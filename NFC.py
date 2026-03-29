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
from smartcard.CardMonitoring import CardObserver
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
def _points_for_event(event_name): 
    if event_name.endswith("Social"): 
        return 30
    elif event_name.endswith(("PD", "CFC")):
        return 40
    elif event_name.endswith("GM"):
        return  50
    elif event_name.endswith("Volunteer"):
        return  90
    elif event_name.endswith("Custom"):
        return  100
    
def award_points(row_num, event_name):
    headers = get_headers()
    
    points = _points_for_event(event_name)
    
    # Find/Alert event col 
    if event_name in headers: 
        event_col = headers.index(event_name)+1
    else: 
        print(f"WARNING: Event column '{event_name}' not found in sheet")
        return 0
    
    # Formating 
    
    sheet.update_cell(row_num, event_col, points)
    format_event_cell(row_num, event_col)
  
    # Recalculate Total 
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
    format_total_points_cell(row_num)
    return points 

def map_uid_to_row(row_num, uid):
    # writes UID -> "Cougar Card UID"
    headers = get_headers()
    uid_col = headers.index("Cougar Card UID") +1
    sheet.update_cell(row_num, uid_col, uid)

def create_new_row(uid, uh_id, first_name, last_name, email, event_name):
    # Create new member entry for new members 
    headers = get_headers()
    
    points = _points_for_event(event_name)
    
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
    
    first_col_val = sheet.col_values(1) # count non-empty rows in column A 
    new_row_num = len(first_col_val)
    print(f"New row created for {first_name} {last_name}")
    
    # Formatting! 
    if event_name in headers: 
        event_col = headers.index(event_name)+1
        format_event_cell(new_row_num, event_col)
    
    format_paid_status_cell(new_row_num, "Unpaid")
    format_entire_sheet()
    
    return new_row_num

# ---- Google Sheets Formatting ---- #

def hex_to_rgb(hex_color):
    hex_color = hex_color.lstrip("#")
    r,g,b = int(hex_color[0:2],16), int(hex_color[2:4],16), int(hex_color[4:6],16)
    return{
        "red": r /255,
        "green": g /255,
        "blue": b / 255}
    
def _range_spec(row, col, spreadsheet_id, sheet_id):
    return{
        "sheetId": sheet_id,
        "startRowIndex": row-1,
        "endRowIndex": row,
        "startColumnIndex": col-1, 
        "endColumnIndex": col
        }

def format_cell_background(row, col, hex_color):
    spreadsheet = client.open(SPREADSHEET_NAME)
    spreadsheet_id = spreadsheet.id
    sheet_id = sheet.id
    
    body = {
        "requests": [
            {
                "repeatCell": {
                    "range": _range_spec(row, col, spreadsheet_id, sheet_id),
                    "cell": {
                        "userEnteredFormat": {
                            "backgroundColor": hex_to_rgb(hex_color)
                            }
                        },
                    "fields": "userEnteredFormat.backgroundColor"
                    }
                }
            ]
        }
    spreadsheet.batch_update(body)
    
def format_paid_status_cell(row_num, paid_status):
    headers = get_headers()
    paid_col = headers.index("Paid Status") + 1 # converts to 1-based (google sheets)
    
    if paid_status == "Paid":
        color = "#c6efce"
    else: 
        color = "#ffc7ce"
    
    format_cell_background(row_num, paid_col, color)

def format_total_points_cell(row_num):
    headers = get_headers()
    total_pts_col = headers.index("Total Points") +1 
    
    format_cell_background(row_num, total_pts_col, "#a4c2f4")
    
    spreadsheet = client.open(SPREADSHEET_NAME)
    sheet_id = sheet.id
    
    body = {
        "requests": [
            {
                "repeatCell": {
                    "range": _range_spec(row_num, total_pts_col, spreadsheet.id, sheet_id), 
                    "cell": {
                        "userEnteredFormat": {
                            "backgroundColor": hex_to_rgb("#a4c2f4"),
                            "textFormat": {
                                "bold": True    
                            }, 
                            "borders": {
                                "top":      {"style": "SOLID"},
                                "bottom":   {"style": "SOLID"},
                                "right":    {"style": "SOLID"},
                                "left":     {"style": "SOLID"} 
                            }
                        }
                    }, 
                    "fields": "userEnteredFormat.backgroundColor, userEnteredFormat.textFormat.bold, userEnteredFormat.borders"
                }
            }
        ]
    }
    spreadsheet.batch_update(body)
    

def format_event_cell(row_num, event_col):
    event_color = "#b7e1cd"
    
    format_cell_background(row_num, event_col, event_color)

def format_entire_sheet():
    spreadsheet = client.open(SPREADSHEET_NAME)
    sheet_id = sheet.id
    
    col_count_val = sheet.row_values(1)
    last_col = len(col_count_val)
    
    first_col_val = sheet.col_values(1) # count non-empty rows in column A 
    last_row = len(first_col_val)
    
    requests = [
        {
            "repeatCell": {
                "range": {
                    "sheetId":          sheet_id, 
                    "startRowIndex":    1,
                    "endRowIndex":      last_row, 
                    "startColumnIndex":    0, 
                    "endColumnIndex":      last_col, 
                    }, 
                "cell": {
                    "userEnteredFormat": {
                        "horizontalAlignment": "CENTER", 
                        "textFormat": {
                            "fontFamily": "Merriweather",
                            "fontSize":     11
                        }
                        }
                    },
                "fields": "userEnteredFormat.horizontalAlignment, userEnteredFormat.textFormat.fontFamily, userEnteredFormat.textFormat.fontSize"
                } 
            }
        ]
    
    if last_col >= 7:
        requests.append({
            "autoResizeDimensions": {
                "dimensions": {
                    "sheetId":      sheet_id,
                    "dimension":    "COLUMNS",
                    "startIndex":    6, 
                    "endIndex":      last_col, 
                    }
                }
            })
    spreadsheet.batch_update({"requests": requests})
    
    
    
# ============================================================================
#                                    NFC
# ============================================================================

GET_UID = [0xFF, 0xCA, 0x00, 0x00, 0x00]

class NFC(CardObserver):
    def __init__(self, event_name):
        self.event_name = event_name
        # self.ready = False # ignore events until reader settles 
    
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
        
        while True: 
            uh_id = input("Enter UH ID: ").strip()
            if not uh_id:
                print("Skipped")
                return 
            
            row_num, row_data = find_row_by_uhid(uh_id)
            
            # ---- Case 2.1: UH ID Found ---- # 
            if row_num:
                headers = get_headers()
                first_name = row_data[headers.index("First Name")]
                last_name = row_data[headers.index("Last Name")]
                
                confirm = input(f"Is this you: {first_name} {last_name}? y/n: ").strip().lower()
                if confirm == "y":
                    map_uid_to_row(row_num, uid)
                    points = award_points(row_num, self.event_name)
                    print(f"Card mapped! Welcome Back, {first_name}! +{points} points awarded.")
                    return 
                else: 
                    print("Let's try again.")
                    continue # loops back 
            
            # ---- UH ID Not Found (Wrong Input) ---- #
            correct_id = input(f"UH ID not found. Is this ID correct? \n{uh_id} \n(y/n): ").strip().lower()
            if correct_id == "n": 
                continue # loops back to input correct ID
            else: # the right ID num just not registered 
                break
                    
            
        # ---- Case 2.3: New Member ---- # 
        print("Welcome to SASE! Please complete the registration.")
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
    # def update(self, observable, actions):
    #     # print(f"DEBUG update() called -- ready = {self.ready}")
    #     if not self.ready: 
    #         return # discard the ghost event on start up
        
    #     added_cards, rmved_cards = actions
        
    #     for card in added_cards:
    #         print("Card Detected!")
        
    #         MAX_RETRIES = 3 
    #         for attempt in range(MAX_RETRIES):
    #             try: 
    #                 card.connection = card.createConnection()
    #                 card.connection.connect()
                    
    #                 data, sw1, sw2 = card.connection.transmit(GET_UID)
                    
    #                 if sw1 == 0x90 and sw2 == 0x00:
    #                     UID = toHexString(data)
    #                     UID = UID.replace(" ", "")
    #                     print(f"UID: {UID}")
    #                     self.handle(UID)
    #                 else: 
    #                     print(f"Failed to get UID. Status: {sw1:02X} {sw2:02X} " )
    #                 break # success - exit retry loop 
        
                
    #             except NoCardException:     # [code] works too fast can trigger this
    #                 if attempt < MAX_RETRIES-1: 
    #                     time.sleep(0.3) # wait & retry 
    #                     continue 
    #                 else: 
    #                     print("Card detected but couldn't connect after retries. Try rescanning.")
                    
    #             except CardConnectionException as e:
    #                 print(f"Connection Error: {e}")
    #                 break
            
            
    #     for card in rmved_cards:
    #         print("Card Removed")
            
        


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
  
    """ CardMonitor + Pyscard has a bug on Mac that glitches out and prevent 
    cards from scanning and the programming running so im discarding this method"""
    # monitor = CardMonitor()
    # observer = NFC(event_name)
    # monitor.addObserver(observer)
    
    # time.sleep(0.5)
    # observer.ready = True
    # print("Ready! Waiting for NFC Card...")
    
    # try: 
    #     while True: 
    #         time.sleep(1)
    
    reader = available_readers[0]
    nfc = NFC(event_name)
    
    print("Ready! Waiting for NFC Card...")
    
    # prevents double scanning ID
    last_uid = None 
    
    try: 
        while True: 
            try: 
                connection = reader.createConnection()
                connection.connect()
                
                data, sw1, sw2 = connection.transmit(GET_UID)
                
                if sw1 == 0x90 and sw2 == 0x00:
                    UID = toHexString(data).replace(" ", "")
                    
                    if UID != last_uid: 
                        print(f"Card Detected! UID: {UID}")
                        last_uid = UID
                        nfc.handle(UID)
            except NoCardException:
                last_uid = None # card removed, reset so next scan works 
            except CardConnectionException: 
                last_uid = None 
            
            time.sleep(0.5) # poll
    
            
    except KeyboardInterrupt:
        print("\nStopped By User")
        
    # finally: 
    #     monitor.deleteObserver(observer)

if __name__ == "__main__":
    main()