#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Thu Feb 26 04:23:00 2026

@author: kongimong
"""

import time 

# shows avaibale readers 
from smartcard.System import readers 

# turns [0xFF, 0xCA, 0x00, 0x00, 0,x00] to string 
from smartcard.util import toHexString

# card insertion/removals 
from smartcard.CardMonitoring import CardMonitor, CardObserver
from smartcard.Exceptions import CardConnectionException

GET_UID = [0xFF, 0xCA, 0x00, 0x00, 0x00]

class NFC(CardObserver):
    
    # overrding CardObserver base class update() | actions returns tuple
    def update(self, observable, actions):
        added_cards, rmved_cards = actions
        
        for card in added_cards:
            print("Card Detected!")
            try: 
                card.connection = card.createConnection()
                card.connection.connect()
                
                data, sw1, sw2 = card.connection.transmit(GET_UID)
                
                if sw1 == 0x90 and sw2 == 0x00:
                    UID = toHexString(data)
                    UID = UID.replace(" ", "")
                    print(f"UID: {UID}")
                else: 
                    print(f"Failed to get UID. Status: {sw1:02X} {sw2:02X} " )
                    
            except CardConnectionException as e:
                print(f"Connection Error: {e}")
        
        for card in rmved_cards:
            print("Card Removed")

def main(): 
    available_readers = readers()
    if not available_readers:
        print("No readers found.")
        return 
    
    print("Available Readers:")
    for i, r in enumerate(available_readers):
        print(f"     [{i}] {r}")
    print()
    print("Waiting for NFC Card...")
    
    monitor = CardMonitor()
    observer = NFC()
    monitor.addObserver(observer)
    
    try: 
        while True: 
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nStopped By User")
    finally: 
        monitor.deleteObserver(observer)

if __name__ == "__main__":
    main()