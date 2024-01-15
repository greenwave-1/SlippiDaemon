import random
import socket
import ubjson
import datetime
import os


# represents a wii connection detected by its udp broadcast
class SlippiConnectionBroadcast:
    def __init__(self, packet, ipAddr, manualAdd=False):
        self.validWii = False
        if manualAdd:
            self.ipAddr = ipAddr
            self.consoleNick = "Manually Added Wii"
            return
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

    def getStr(self):
        return self.ipAddr + " | " + self.consoleNick


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
        self.establishedConnection = False
        self.consoleNick = None
        self.nintendontVersion = "-1"
        # four bytes after this are the len of the data section, can be all 0's (but shouldn't be)
        self.SLIPPI_FILE_HEADER = b'\x7b\x55\x03\x72\x61\x77\x5b\x24\x55\x23\x6c'

        # working network data stuff
        self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.slippi_net_ip = None
        self.slippi_net_port = 51441  # 51441 is default
        self.game_payloads = []
        self.complete_payloads = []
        self.workingPacket = bytearray()
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

    def setConnection(self, ip, port=None):
        self.slippi_net_ip = ip
        if port is not None:
            self.slippi_net_port = port

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

    def attemptEstablishConnection(self):
        self.socket.connect((self.slippi_net_ip, self.slippi_net_port))

        # setup initial handshake
        temp = {}
        temp["type"] = 1
        temp["payload"] = self.jsonObj
        encoded = ubjson.dumpb(temp)
        handshake = bytes(len(encoded).to_bytes(4, byteorder='big', signed=False)) + encoded
        self.socket.sendall(handshake)

        # get and interpret data from wii
        # TODO: probably should be some error checking here
        data = self.socket.recv(4096)
        data_decoded = ubjson.loadb(data[4:])["payload"]
        self.establishedConnection = True
        # set data that we get
        self.nintendontVersion = data_decoded["nintendontVersion"]
        self.jsonObj["clientToken"] = int.from_bytes(data_decoded["clientToken"], byteorder="big")
        self.payload_cursor = int.from_bytes(data_decoded["pos"])
        if self.consoleNick is None:
            self.consoleNick = data_decoded["nick"]

        if self.relayEnabled:
            print("waiting for relay connection")
            self.relaySocket.listen()
            self.relayConn, addr = self.relaySocket.accept()
            self.relayConn.sendall(data)

    def getNetworkData(self):
        if not self.establishedConnection:
            self.attemptEstablishConnection()
            # TODO: leave code here if connect fails

        # get our packet
        data = self.socket.recv(4096)
        self.workingPacket += data

        # logic copied from official library:
        # https://github.com/project-slippi/slippi-js/blob/efbafa721e272283a7924975f1dc8295ac522dac/src/console/communication.ts#L32C2
        while len(self.workingPacket) >= 4:
            # get size
            msgLen = int.from_bytes(self.workingPacket[:4], byteorder="big", signed=False)

            # do we have all the data we need?
            if len(self.workingPacket) < msgLen + 4:
                # we need another packet, we don't have full data
                # break instead of continue because this function will still process complete data below this loop
                break

            # get the message
            decodedData = self.workingPacket[4:msgLen + 4]
            self.complete_payloads.append(ubjson.loadb(decodedData))  # TODO: don't convert here so that relay functionality works again

            # remove data we processed
            self.workingPacket = self.workingPacket[msgLen + 4:]

        for payload in self.complete_payloads:
            # no idea if this is fixed or not
            if len(payload) == 0:
                print("Zero len payload in complete payload list? how?")
                exit(1)

            # TODO: either store the payloads undecoded to send here or reencode them
            # TODO: this will not work whatsoever until then
            if self.relayEnabled and False:
                relayPayload = len(payload).to_bytes(4, byteorder='big', signed=False) + payload
                try:
                    self.relayConn.sendall(relayPayload)
                except socket.error:
                    print("socket error")
                    self.relayEnabled = False

            # start checking data itself
            # type 2 is replay data
            if payload['type'] == 2:
                if self.payload_cursor == int.from_bytes(payload["payload"]["pos"]):
                    # check for start of game
                    # this is technically checking for the "Event payloads" section and not the "game start" section
                    if payload["payload"]["data"][0] == 0x35:
                        print("game start")
                        # check if data hasn't been written (ie we missed the end game signal)
                        if len(self.game_payloads) != 0:
                            # forward one payload because if the detection didn't trigger we probably missed it?
                            # _supposedly_ this can happen, idk if this has been fixed or not
                            # I am completely guessing that this will work, I have no idea
                            self.metadata["lastFrame"] = int.from_bytes(self.game_payloads[-1][1:5], byteorder="big", signed=True)
                            self.writeFile()
                        self.startTimeStr = datetime.datetime.now().strftime("%Y-%m-%dT%H%M%S")
                        self.metadata["startAt"] = datetime.datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%SZ')

                    self.game_payloads.append(payload["payload"]["data"])
                    self.dataLen += len(payload["payload"]["data"])
                    self.payload_cursor = int.from_bytes(payload["payload"]["nextPos"])

                    # check for end of game
                    if payload["payload"]["data"][0] == 0x39:
                        print("end of replay detected")
                        # end of replay
                        # get last frame
                        self.metadata["lastFrame"] = int.from_bytes(self.game_payloads[-2][1:5], byteorder="big", signed=True)
                        # write file
                        self.writeFile()
                else:
                    print("payload is not the expected pointer")
                    print("expected:", self.payload_cursor)
                    pass
            else:
                #print("payload is not type 2")
                pass

        self.complete_payloads.clear()
