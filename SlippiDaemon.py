import random
import socket
import ubjson
import datetime
import os

# represents a wii connection detected by its udp broadcast
class SlippiConnectionBroadcast:
    def __init__(self, packet, ipAddr):
        self.validWii = False
        if packet[:10] == b"SLIP_READY":
            self.validWii = True
            # https://github.com/project-slippi/slippi-launcher/blob/e92a5e9cb2cd0eeac2015e715bedb490557f429f/src/console/connectionScanner.ts#L32
            self.macAddr = packet[10:16]  # probably not needed? its provided though, so grab it
            self.consoleNick = packet[16:48].decode().replace('\x00', '')  # strip null chars from name
            self.ipAddr = ipAddr

    def isValid(self):
        if self.validWii:
            return self.validWii

    def getNick(self):
        if self.validWii:
            return self.consoleNick

    def getIP(self):
        if self.validWii:
            return self.ipAddr


# scans and returns any wiis found via udp broadcast
class SlippiConnectionScanner:
    def __init__(self):
        self.connectionList = []
        self.broadcastSocket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.broadcastSocket.bind(('', 20582))
        self.broadcastSocket.settimeout(3)

    def scan(self):
        try:
            data, addr = self.broadcastSocket.recvfrom(4096)
        except socket.error:
            return

        conn = SlippiConnectionBroadcast(data, addr[0])
        if conn.isValid():
            if any(item.macAddr == conn.macAddr for item in self.connectionList):  # i think this does what I want?
                return
            else:
                self.connectionList.append(conn)

    def getList(self):
        return self.connectionList


class SlippiDaemon:
    def __init__(self, scannedConnection=None):
        # set the stuff used for the initial handshake
        self.jsonObj = {}
        self.jsonObj["cursor"] = bytearray([0, 0, 0, 0, 0, 0, 0, 0])
        self.jsonObj["clientToken"] = bytearray([0, 0, 0, 0])
        self.jsonObj["isRealTime"] = False

        # stuff for the slippi file itself
        self.startTimeStr = "1970-01-01T000000"
        self.dataLen = 0
        self.fileCounter = 0
        self.establishedConnection = False
        self.consoleNick = "Temp"
        self.nintendontVersion = "-1"
        # four bytes after this are the len of the data section, can be all 0's (but shouldn't be)
        self.SLIPPI_FILE_HEADER = b'\x7b\x55\x03\x72\x61\x77\x5b\x24\x55\x23\x6c'

        # working network data stuff
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.slippi_net_ip = None
        self.slippi_net_port = None  # 51441 is default
        self.game_payloads = []
        self.complete_payloads = []
        self.incomplete_payload_data = None
        self.incomplete_payload_len_remaining = 0
        self.payload_cursor = -1

        if scannedConnection is not None:
            self.consoleNick = scannedConnection.getNick()
            self.setConnection(scannedConnection.getIP())

        # TODO: need to parse data live and add this, but stuff like slp/peppi and py-slippi complain if this stuff isn't present at all
        self.metadata = {}
        self.metadata["startAt"] = self.startTimeStr
        self.metadata["lastFrame"] = -123
        self.metadata_players = {}  # TODO: this needs to be done probably?
        self.metadata["players"] = self.metadata_players
        self.metadata["playedOn"] = "network"
        self.metadata["consoleNick"] = self.consoleNick

        # relay?
        # TODO: this is barely implemented, needs redone
        self.relayEnabled = False
        self.relayPort = None
        self.relaySocket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.relayConn = None

        # thread stuff
        # TODO: also hacky, like everything else...
        self.shouldRun = True
        self.isRunning = False

    def setConnection(self, ip, port=51441):
        self.slippi_net_ip = ip
        self.slippi_net_port = port

    def getConfigJ(self):
        return self.jsonObj

    def enableRelay(self, port=None):
        # randomly get a port if no port provided, or if provided port is invalid
        if port is None or (port < 1024 or port > 65535):
            self.relayPort = random.randint(60000, 63533)  # arbitrary, top bound is "melee" via t9
        else:
            self.relayPort = port
        self.relaySocket.bind(("127.0.0.1", self.relayPort))  # TODO: this doesn't allow an external connection
        print("relay listening on", self.relayPort)
        self.relayEnabled = True

    def writeFile(self):
        if len(self.game_payloads) == 0:
            return
        # TODO: add ability to set path, and specify not to make folder based on console name
        newFilePath = self.consoleNick + "/Game_" + self.startTimeStr + ".slp"
        os.makedirs(os.path.dirname(newFilePath), exist_ok=True)
        with open(newFilePath, "wb") as outFile:
            outFile.write(self.SLIPPI_FILE_HEADER)
            outFile.write(self.dataLen.to_bytes(4, byteorder='big', signed=False))  # length of data section
            #outFile.write(bytearray([0, 0, 0, 0]))
            for data in self.game_payloads:  # data section
                outFile.write(data)
            # TODO: write metadata block (and also figure out how to generate it lol)
            outFile.write(b'\x55\x08metadata')
            outFile.write(ubjson.dumpb(self.metadata))
            outFile.write(b'\x7d')  # closing brace
            self.game_payloads.clear()
            self.incomplete_payload_data = None
            self.incomplete_payload_len_remaining = 0
            self.payload_cursor = -1
            self.startTimeStr = "1970-01-01T000000"
            self.dataLen = 0
        print("wrote file")

    def closeConnection(self):
        if self.establishedConnection:
            self.socket.close()

    def requestStopProcess(self):
        self.shouldRun = False

    def getRunningStatus(self):
        return self.isRunning

    def runProcess(self):
        self.isRunning = True
        while self.shouldRun:
            self.getNetworkData()
        self.writeFile()
        self.isRunning = False

    def getNetworkData(self):
        if not self.establishedConnection:
            self.socket.connect((self.slippi_net_ip, self.slippi_net_port))
            temp = {}
            temp["type"] = 1
            temp["payload"] = self.getConfigJ()
            encoded = ubjson.dumpb(temp)
            handshake = bytes(len(encoded).to_bytes(4, byteorder='big', signed=False)) + encoded
            self.socket.sendall(handshake)
            data = self.socket.recv(4096)
            print(data)
            self.establishedConnection = True
            # set data that we get, eventually...

            if self.relayEnabled:
                print("waiting for relay connection")
                self.relaySocket.listen()
                self.relayConn, addr = self.relaySocket.accept()
                self.relayConn.sendall(data)

        else:
            data = self.socket.recv(4096)
            working_packet_len = len(data)
            working_packet_slice = data
            print("START: len of packet:", working_packet_len, "\nData:\n", working_packet_slice)

            # do we have an incomplete payload from before?
            if self.incomplete_payload_len_remaining > 0:
                print("incomplete data from before, len:", self.incomplete_payload_len_remaining)
                if self.incomplete_payload_len_remaining > len(data):
                    print("still not complete")
                    self.incomplete_payload_data = self.incomplete_payload_data + bytes(data)
                    self.incomplete_payload_len_remaining = self.incomplete_payload_len_remaining - len(data)
                    return
                else:
                    print("data can be completed?")
                    incomplete_payload_data = self.incomplete_payload_data + bytes(data[:self.incomplete_payload_len_remaining])
                    if len(self.incomplete_payload_data) == 0:
                        print("ZERO LEN DATA PAYLOAD ADDED IN INCOMPLETE SECTION!!!!!!!!")
                    self.complete_payloads.append(incomplete_payload_data)
                    working_packet_slice = data[self.incomplete_payload_len_remaining:]
                    working_packet_len = len(working_packet_slice)
                self.incomplete_payload_data = None
                self.incomplete_payload_len_remaining = 0

            # loop until we've exhausted this packet
            while working_packet_len > 0:
                print("normal data, packet len:", working_packet_len)
                print("data:\n", working_packet_slice)
                # TODO: I have no idea if this is a thing that can happen, mainly this is to try and find
                # TODO: a weird error that I can't replicate
                if working_packet_len < 4:
                    print("payload length is incomplete!!!!!")
                    exit(2)
                # get payload len
                payload_size = int.from_bytes(working_packet_slice[:4])
                # remove len from working data
                working_packet_slice = working_packet_slice[4:]

                if payload_size <= len(working_packet_slice):
                    print("payload size is smaller than data left, whole payload")
                    if len(working_packet_slice[:payload_size]) == 0:
                        print("ZERO LEN DATA PAYLOAD ADDED IN NORMAL SECTION!!!!!!!!!!")
                    self.complete_payloads.append(working_packet_slice[:payload_size])
                    working_packet_slice = working_packet_slice[payload_size:]
                    working_packet_len = len(working_packet_slice)
                    continue
                else:
                    print("incomplete packet started")
                    self.incomplete_payload_data = working_packet_slice
                    self.incomplete_payload_len_remaining = payload_size - len(working_packet_slice)
                    break

            print("payloads:", len(self.complete_payloads))
            for payload in self.complete_payloads:
                print("payload:", payload)
                # todo: why does this happen?
                if len(payload) == 0:
                    print("ZERO LEN DATA PAYLOAD IN THE LIST!!!!!!!!!!")
                    exit(1)
                temp = ubjson.loadb(payload)
                if self.relayEnabled:
                    relayPayload = len(payload).to_bytes(4, byteorder='big', signed=False) + payload
                    try:
                        self.relayConn.sendall(relayPayload)
                    except socket.error:
                        print("socket error")
                        self.relayEnabled = False
                if temp['type'] == 2:
                    print("payload is type 2")
                    # start of a replay
                    # TODO: check for the "start game" command instead of this
                    # TODO: also, implement graceful recovery if there is a network error
                    # TODO: apparently you can pass the cursor of where you want, and if you get it back it works?
                    # TODO: also, really should just set this to what I get from the handshake, and not this hacky thing
                    if self.payload_cursor == -1:
                        print("payload is start of game?")
                        self.startTimeStr = datetime.datetime.now().strftime("%Y-%m-%dT%H%M%S")
                        self.metadata["startAt"] = datetime.datetime.now().strftime('%Y-%m-%dT%H:%M:%SZ')
                        self.payload_cursor = int.from_bytes(temp["payload"]["pos"])
                    if self.payload_cursor == int.from_bytes(temp["payload"]["pos"]):
                        print("got expected payload pointer")
                        self.game_payloads.append(temp["payload"]["data"])
                        self.dataLen += len(temp["payload"]["data"])
                        self.payload_cursor = int.from_bytes(temp["payload"]["nextPos"])
                        # TODO: apparently there's a bug where this won't get sent sometimes? figure out how to handle that
                        if temp["payload"]["data"][0] == 0x39:
                            print("end of replay detected")
                            # end of replay
                            # get last frame
                            self.metadata["lastFrame"] = int.from_bytes(self.game_payloads[-2][1:5], byteorder="big", signed=True)
                            print(self.metadata["lastFrame"])
                            # write file
                            self.writeFile()
                            self.fileCounter += 1
                    else:
                        print("payload is not the expected pointer")
                        print("expected:", self.payload_cursor)
                        pass
                else:
                    print("payload is not type 2")
                    pass

            self.complete_payloads.clear()
