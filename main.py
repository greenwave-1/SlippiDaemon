import SlippiDaemon
import threading
if __name__ == '__main__':


    # scan on local network and auto-add any wiis detected
    '''
    scanner = SlippiDaemon.SlippiConnectionScanner()
    scanner.scan()
    for wii in scanner.getList():
        print(wii.getNic())
        print(wii.getIP())
    exit()


    existingConnections = []
    slippiObjectList = []
    threadList = []

    scanner = SlippiDaemon.SlippiConnectionScanner()
    try:
        while True:
            scanner.scan()
            temp = scanner.getList()
            for item in temp:
                if item not in existingConnections:
                    print("adding connection:", item.getIP(), "|", item.getNick())
                    slippiConnection = SlippiDaemon.SlippiDaemon(item)
                    slippiObjectList.append(slippiConnection)
                    existingConnections.append(item)
            for slippiConnection in slippiObjectList:
                if not slippiConnection.getRunningStatus():
                    print("starting process")
                    t = threading.Thread(target=slippiConnection.runProcess)
                    threadList.append(t)
                    t.start()
    except KeyboardInterrupt:
        print("closing")
        for slippiConnection in slippiObjectList:
            slippiConnection.requestStopProcess()
        for thread in threadList:
            thread.join()
        for slippiConnection in slippiObjectList:
            slippiConnection.closeConnection()

    '''

    # connect to specific wii, mainly for testing
    test = SlippiDaemon.SlippiDaemon()
    #test.setConnection("10.200.200.128")
    test.setConnection("10.20.204.115")
    #test.enableRelay(31902)
    #test.setConnection("127.0.0.1", 53743)
    try:
        while True:
            test.getNetworkData()
    except KeyboardInterrupt:
        print("keyboard interrupt")
        test.closeConnection()

