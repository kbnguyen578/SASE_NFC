#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Thu Feb 26 04:23:00 2026

@author: kongimong
"""

import time 
import gspread 
from google.oauth2.service_account import Credentials 

# shows avaibale readers 
from smartcard.System import readers 

# turns [0xFF, 0xCA, 0x00, 0x00, 0,x00] to string 
from smartcard.util import toHexString

# card insertion/removals 
from smartcard.CardMonitoring import CardMonitor, CardObserver
from smartcard.Exceptions import CardConnectionException, NoCardException

# ============================================================================
#                             Google Sheets
# ============================================================================

# # ---- API call to the member sheet ---- #

SERVICE_ACC_FILE = "sasehubtest-5cfdac0c9557.json"
SPREADSHEET_NAME = "sasehubtest"
OVERVIEW_SHEET = "Total Points Overview"

creds = Credentials.from_service_account_file(
    SERVICE_ACC_FILE,
    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive"
        ]
    )

client = gspread.authorize(creds)

sheet = client.open(SPREADSHEET_NAME).worksheet(OVERVIEW_SHEET)

# all_rows = sheet.get_all_values()

# ---- Sheet Helpers ---- #
def get_headers():
    return sheet.row_values(1)

def find_row_by_uid(uid):
    # return (row_index_1based, row_data) / (None, None)
    headers = get_headers()
    uid_col = headers.index("Cougar Card UID") +1 
    all_uids = sheet.col_values(uid_col)
    for i, cell in enumerate(all_uids):
        if cell.strip() == uid.strip(): 
            return i+1, sheet.row_values(i+1)
    
    return None, None

def find_row_by_uhid(uh_id):
    headers = get_headers()
    uhid_col = headers.index("UH ID") +1 
    all_uhids = sheet.col_values(uhid_col)
    clean_search = ''.join(filter(str.isdigit, uh_id))
    for i, cell in enumerate(all_uhids):
        if ''.join(filter(str.isdigit, cell)) == clean_search:
            return i+1, sheet.row_values(i+1)
    return None, None

def get_event_headers():
    # return ALL column headers after "Total Points"
    headers = get_headers()
    total_points_index = headers.index("Total Points")
    events = [h for h in headers[total_points_index+1:] if h.strip()]
    return events 

def select_event(): 
    # fetches event from the sheet, pick one 
    print("fetching events from sheet...")
    events = get_event_headers()
    
    if not events: 
        print("No event columns found. Add one to the sheet first.")
        return None
  
    print("\nAvailable Events:")
    for i, name in enumerate(events):
        print(f" [{i +1}] {name}")
    
    while True:
        choice = input("\nSelect event number: ").strip()
        if choice.isdigit() and 1 <= int(choice) <= len(events):
            selected = events[int(choice) -1]
            print(f"\nEvent set to {selected}\n")
            return selected 
        print("Invalid choice. Try again.")

def award_points(row_num, event_name):
    headers = get_headers()
    
    points = 0
    if event_name.endswith("Social"): 
        points = 30
    elif event_name.endswith(("PD", "CFC")):
        points = 40
    elif event_name.endswith("GM"):
        points = 50
    elif event_name.endswith("Volunteer"):
        points = 90
    elif event_name.endswith("Custom"):
        points = 100
    
    # Find/Alert event col 
    if event_name in headers: 
        event_col = headers.index(event_name)+1
    else: 
        print(f"WARNING: Event column '{event_name}' not found in sheet")
        return 0
    
    sheet.update_cell(row_num, event_col, points)
    row_data = sheet.row_values(row_num)
    paid_status = row_data[headers.index("Paid Status")]
    total_points_col = headers.index("Total Points")
    
    total = 50 if paid_status == "Paid" else 0
    for val in row_data[total_points_col+1:]:
        try:
            total += int(val)
        except (ValueError, TypeError):
            pass 
    
    sheet.update_cell(row_num, total_points_col+1, total)
    return points 

def map_uid_to_row(row_num, uid):
    # writes UID -> "Cougar Card UID"
    headers = get_headers()
    uid_col = headers.index("Cougar Card UID") +1
    sheet.update_cell(row_num, uid_col, uid)

def create_new_row(uid, uh_id, first_name, last_name, email, event_name):
    # Create new member entry for new members 
    headers = get_headers()
    
    points = 0
    if event_name.endswith("Social"): 
        points = 30
    elif event_name.endswith(("PD", "CFC")):
        points = 40
    elif event_name.endswith("GM"):
        points = 50
    elif event_name.endswith("Volunteer"):
        points = 90
    elif event_name.endswith("Custom"):
        points = 100
    
    # Build row (fixed 7 columns)
    row = [""] * max(len(headers), 7)
    row[headers.index("First Name")]            = first_name 
    row[headers.index("Last Name")]             = last_name 
    row[headers.index("Email")]                 = email
    row[headers.index("UH ID")]                 = uh_id
    row[headers.index("Cougar Card UID")]       = uid
    row[headers.index("Paid Status")]           = "Unpaid"
    row[headers.index("Total Points")]          = points    
    
    if event_name in headers: 
        row[headers.index(event_name)] = points
    
    sheet.append_row(row)
    new_row_num = sheet.row_count
    print(f"New row created for {first_name} {last_name}")
    return new_row_num
    
# ============================================================================
#                                    NFC
# ============================================================================

GET_UID = [0xFF, 0xCA, 0x00, 0x00, 0x00]

class NFC(CardObserver):
    def __init__(self, event_name):
        self.event_name = event_name
    
    def handle(self, uid):
        # ---- Case 1: Registered UID---- #
        row_num, row_data = find_row_by_uid(uid)
        
        if row_num:
            headers = get_headers()
            first_name = row_data[headers.index("First Name")]
            points = award_points(row_num, self.event_name)
            print(f"Welcome Back, {first_name}! +{points} points awarded.")
            return 
        
        # ---- Case 2: UID Unregistered ---- # 
        print("WARNING: CARD NOT REGISTERED")
        uh_id = input("Enter UH ID: ").strip()
        if not uh_id:
            print("Skipped")
            return 
        
        row_num, row_data = find_row_by_uhid(uh_id)
        
        # ---- Case 2.1: UH ID Found ---- # 
        if row_num:
            map_uid_to_row(row_num, uid)
            headers = get_headers()
            first_name = row_data[headers.index("First Name")]
            points = award_points(row_num, self.event_name)
            print(f"Card mapped! Welcome Back, {first_name}! +{points} points awarded.")
            return 
        
        # ---- Case 2.2: New Member ---- # 
        print("UH ID not found. Please complete registration.")
        first_name = input("First name: ").strip()
        last_name = input("Last name: ").strip()
        email = input("Email (press Enter to skip): ").strip()
        
        if not first_name or not last_name:
            print("First and last name required. Skipped.")
            return 
        
        row_num = create_new_row(uid, uh_id, first_name, last_name, email, self.event_name)
        points = award_points(row_num, self.event_name)
        print(f"Registered! Welcome, {first_name}! +{points} points awarded.")
        
    
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
                    self.handle(UID)
                else: 
                    print(f"Failed to get UID. Status: {sw1:02X} {sw2:02X} " )
                    
            
            except NoCardException:
                # [code] works too fast can trigger this
                print("No card present (ignored)")
                pass
                
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
    
    # Select event before starting!!! 
    event_name = select_event()
    if not event_name:
        return 
    
    print("Waiting for NFC Card...")
    
  
    monitor = CardMonitor()
    observer = NFC(event_name)
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