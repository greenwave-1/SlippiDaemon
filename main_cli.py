import SlippiDaemon
import threading

if __name__ == '__main__':

    # managing vars for the cli
    shouldListenLoopRun = True
    shouldCheckForWiis = True
    shouldAutoAddWiis = True
    shouldAutoStartDaemon = True
    existingConnections = []
    slippiObjectList = []
    threadList = []

    # function that listens for wiis on a thread (ie not blocking main thread for cli)
    def CLI_Listen_Loop():
        scanner = SlippiDaemon.SlippiConnectionScanner()
        while shouldListenLoopRun:
            if shouldCheckForWiis:
                scanner.scan()
                returnedWiis = scanner.getList()
                for wii in returnedWiis:
                    if wii not in existingConnections and shouldAutoAddWiis:
                        slippiConnection = SlippiDaemon.SlippiDaemon(wii)
                        slippiObjectList.append(slippiConnection)
                        existingConnections.append(wii)
                    for slippiConnection in slippiObjectList:
                        if not slippiConnection.getRunningStatus() and shouldAutoStartDaemon:
                            print("starting wii")
                            t = threading.Thread(target=slippiConnection.runProcess)
                            threadList.append(t)
                            t.start()


    # start listen thread
    listenThread = threading.Thread(target=CLI_Listen_Loop)
    listenThread.start()

    # cli man loop
    print("Type \"help\" for a list of commands.")
    while True:
        cmd = input("> ").strip().lower().split(' ')
        match cmd[0]:
            case "help":
                print("help: display this message\n"
                      "list <arg>: list wiis, flags are:\n"
                      "\tdetected: shows all wiis detected\n"
                      "\tconnected: shows all wiis connected\n"
                      "add <ip addr>: adds wii\n"
                      "set <arg> true/false: sets flags used by program, flags are:\n"
                      "\tautocheck: whether the daemon will listen for wiis at all\n"
                      "\tautoadd: whether the deamon automatically creates the object\n"
                      "\tautostart: whether or not the daemon starts listening for replays\n"
                      "exit: exits the program")

            case "list":
                if len(cmd) < 2:
                    print("Detected Wiis:")
                    for wii in existingConnections:
                        print(wii.getStr())
                    continue
                match cmd[1]:
                    case "detected":
                        print("Detected Wiis:")
                        for wii in existingConnections:
                            print(wii.getStr())
                    case "connected":
                        print("Connected Wiis:")
                        for slippiObject in slippiObjectList:
                            print(slippiObject.getStr())


            case "add":
                if len(cmd) > 1:
                    print(cmd[1])
                    temp2 = SlippiDaemon.SlippiConnectionBroadcast(None, cmd[1], True)
                    temp = SlippiDaemon.SlippiDaemon(scannedConnection=temp2)
                    if not temp.getRunningStatus() and shouldAutoStartDaemon:
                        t = threading.Thread(target=temp.runProcess)
                        threadList.append(t)
                        t.start()
                    slippiObjectList.append(temp)
                    existingConnections.append(temp2)
            case "set":
                match cmd[1]:
                    case "autocheck":
                        if cmd[2] == "true" or cmd[2] == "t":
                            shouldCheckForWiis = True
                        elif cmd[2] == "false" or cmd[2] == "f":
                            shouldCheckForWiis = False
                    case "autoadd":
                        if cmd[2] == "true" or cmd[2] == "t":
                            shouldAutoAddWiis = True
                        elif cmd[2] == "false" or cmd[2] == "f":
                            shouldAutoAddWiis = False
                    case "autostart":
                        if cmd[2] == "true" or cmd[2] == "t":
                            shouldAutoStartDaemon = True
                        elif cmd[2] == "false" or cmd[2] == "f":
                            shouldAutoStartDaemon = False

            case "exit":
                shouldListenLoopRun = False
                listenThread.join()
                for slippiConnection in slippiObjectList:
                    slippiConnection.requestStopProcess()
                for thread in threadList:
                    thread.join()
                for slippiConnection in slippiObjectList:
                    slippiConnection.closeConnection()
                exit()
