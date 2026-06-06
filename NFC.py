#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Thu Feb 26 04:23:00 2026

@author: kongimong
"""

import time 
import gspread 
from google.oauth2.service_account import Credentials 
import json

# shows avaibale readers 
from smartcard.System import readers 

# turns [0xFF, 0xCA, 0x00, 0x00, 0,x00] to string 
from smartcard.util import toHexString

# card insertion/removals 
from smartcard.CardMonitoring import CardObserver
from smartcard.Exceptions import CardConnectionException, NoCardException

# for UI
import tkinter as tk
from tkinter import font as tkfont
import threading 
from PIL import Image, ImageTk 

# ============================================================================
#                             Google Sheets
# ============================================================================

# # ---- API call to the member sheet ---- #

SERVICE_ACC_FILE = "virtual-events-queue-c87627c032e3.json"
SPREADSHEET_NAME = "SP26 Member Overview"
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

EXCLUDED_SHEETS = {"Membership", OVERVIEW_SHEET}

with open("virtual-events-queue-c87627c032e3.json") as f:
    print(json.load(f)["client_email"])

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

def get_event_tabs(): 
    spreadsheet = client.open(SPREADSHEET_NAME)
    all_sheets = spreadsheet.worksheets()
    
    event_tabs = [ws.title for ws in all_sheets if ws.title != EXCLUDED_SHEETS]
    
    return event_tabs

def select_event(): 
    # fetches event from the sheet, pick one 
    print("fetching events from sheet...")
    events = get_event_tabs()
    
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
    elif event_name.endswith(("PD", "CFC", "Fundraising")):
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
        
        new_col = len(headers)+1
        sheet.update_cell(1, new_col, event_name)
        
        spreadsheet = client.open(SPREADSHEET_NAME)
        sheet_id = sheet.id
        spreadsheet.batch_update(
            {
                "requests": [{
                    "repeatCell": {
                        "range": {
                            "sheetId":          sheet_id, 
                            "startRowIndex":    0, 
                            "endRowIndex":      1, 
                            "startColumnIndex": new_col -1, 
                            "endColumnIndex":   new_col
                        }, 
                        "cell": {
                            "userEnteredFormat": {
                                "backgroundColor": hex_to_rgb("#fce5cd"),
                                "textFormat": {"bold": True}
                            }
                        },
                        "fields": "userEnteredFormat.backgroundColor, userEnteredFormat.textFormat.bold"
                    }    
                }]    
            })
        
        event_col = new_col
        print(f"Create new event column: '{event_name}' at col {new_col}")
        format_entire_sheet()
        
        headers = get_headers()
    
    ### Edge Case: Already Checked-In ###
    existing = sheet.cell(row_num, event_col).value
    if existing: 
        print("Already checked in for this event!")
        return None
    
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

# ------------------------- Google Sheets Formatting ------------------------- #

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
    event_color = "#d9d2e9"
    
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
                    "startRowIndex":    0,
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
                    if points: 
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
 
# ============================================================================
#                                  Python GUI
# ============================================================================           

BG_COLOR = "#f0ece4"
CHK_COLOR = "#a2af7e"
X_COLOR = "#cc776d"
INPUT_BG = "#d9dac6"
BORDER = "#547219"
INPUT_TEXT = "#96a66f"
DISCLAIMER = "#605e5b"
EVENT_BG = "#dde1bf"
DRP_DWN_BUTTON = "#9fb06e"
EVENT_TEXT = "#607f1d"

SCREEN_W = 870
SCREEN_H = 614

class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("SASE Check-In")
        self.geometry(f"{SCREEN_W}x{SCREEN_H}")
        self.resizable(False, False)
        self.configure(bg = BG_COLOR)
        
        self.event_name = None 
        self.current_uid = None 
        self.current_uhid = None 
        self._nfc_thraed = None 
        
        self.f_title = tkfont.Font(family="Georgia", size = 30, weight = "bold")
        self.f_sub = tkfont.Font(family="Georgia", size = 16)
        self.f_small = tkfont.Font(family="Georgia", size = 14)
        self.f_btn = tkfont.Font(family="Georgia", size = 16, weight = "bold")
        self.f_label = tkfont.Font(family="Georgia", size = 20)
        self.f_badge = tkfont.Font(family="Georgia", size = 12)
        
        self._frame = None 
        self.show_event_select()
    
    # ---- Fram Switcher ---- # 
    def _switch(self, new_frame_cls, *args, **kwargs):
        if self._frame: 
            self._frame.destroy()
        self._frame = new_frame_cls(self, *args, **kwargs)
        self._frame.place(x=0, y=0, width = SCREEN_W, height = SCREEN_H)
    
    # ---- Screen Launchers ---- # 
    def show_event_select(self):
        self._switch(EventSelectScreen)
    
    def show_scan(self):
        self._switch(ScanScreen)
    
    def show_success(self, msg, pts): 
        self._switch(SuccessScreen, message=msg, points=pts)
    
    def show_already_in(self):
        self._switch(AlreadyInScreen)
    
    def show_uhid_entry(self, uid):
        self._current_uid = uid
        self._switch(UHIDScreen)
    
    def show_confirm_identity(self, fName, lName, rNum):
        self._switch(ConfirmScreen, 
                     first_name = fName, 
                     last_name = lName, 
                     row_num = rNum)
    
    def show_registration(self, uid, uh_id):
        self._switch(RegistrationScreen, uid=uid, uh_id = uh_id)
    
    def show_card_mapped(self, first_name, pts): 
        self._switch(SuccessScreen, message = f"Card mapped! Welcome back, \n{first_name}!", 
                     points=pts)

# ------------------------- Google Sheets Formatting ------------------------- #
def _make_card(parent, app):
    outer = tk.Frame(parent, bg = BG_COLOR)
    outer.place(x=0, y=0, width = SCREEN_W, height=SCREEN_H)
    
    card = tk.Frame(outer, bg = BG_COLOR, bd=0, highlightthickness=0)
    card.place(relx=.5, rely=.5, anchor="center", width = SCREEN_W-60, height=SCREEN_H-80)
    
    if app.event_name: 
        badge_text = app.event_name 
        badge = tk.Label(outer, text=f"{badge_text}", 
                         bg = BG_COLOR, fg = "black", 
                         font = app.f_badge, padx = 0, pady = 0)
        badge.place(x=10, y = 590)
    
    return outer, card

class EventSelectScreen(tk.Frame):
    def __init__(self, master): 
        super().__init__(master, bg=BG_COLOR)
        app = master
        
        tk.Label(self, 
                 text = "SASE Check-In",
                 font=app.f_title,
                 bg=BG_COLOR, fg="black").place(relx=.5, y = 70, anchor="center")
        tk.Label(self, text="Select today's event to begin",
                 font=app.f_sub, bg=BG_COLOR, fg=EVENT_TEXT).place(relx=0.5, y=110, anchor="center")
        
        self._var = tk.StringVar(value="Loading events...")
        self._dropdown = tk.OptionMenu(self, self._var, "Loading events...")
        self._dropdown.config(font=app.f_small, bg=BG_COLOR, fg="black",
                              activebackground=EVENT_BG, activeforeground="white",
                              highlightthickness=0, bd=0, width=36)
        self._dropdown["menu"].config(font=app.f_small, bg=BG_COLOR, fg="black")
        self._dropdown.place(relx=0.5, y=200, anchor="center")
        
        def load_events(): 
            try: 
                events = get_event_tabs()
            except Exception as e:
                events = []
                print("Error fetching events:", e)
            master.after(0, lambda: self._populate(events, app))
            
        threading.Thread(target=load_events, daemon=True).start()
    
    def _populate(self, events, app):
        if not events: 
            self._var.set("No events found")
            return 
        
        self._var.set(events[0])
        menu = self._dropdown["menu"]
        menu.delete(0, "end")
        for ev in events: 
            menu.add_command(label=ev, command=lambda e = ev: self._var.set(e))
        
        def confirm():
            chosen = self._var.get()
            if chosen and chosen != "Loading events...":
                app.event_name = chosen
                app.show_scan()
                
        self._btn_img = ImageTk.PhotoImage(Image.open("Confirm_Button.png").resize((300,45)))
        
        btn = tk.Label(self, image=self._btn_img, cursor = "hand2", bg=BG_COLOR, bd = 0)
        btn.place(relx=0.5,y = SCREEN_H-100, anchor="center")
        btn.bind("<Button-1>", lambda e: confirm())
        
        # tk.Button(self, text="Confirm Event →",
        #   font=app.f_btn, bg=EVENT_BG, fg=BORDER,
        #   activebackground=EVENT_BG, activeforeground=CHK_COLOR,
        #   bd=0, relief="flat", overrelief="flat",        # ← add these
        #   padx=20, pady=10, cursor="hand2",
        #   command=confirm).place(relx=0.5, y=SCREEN_H - 55, anchor="center")
            
class ScanScreen(tk.Frame):
    def __init__(self, master): 
        super().__init__(master, bg=BG_COLOR)
        app = master
        
        outer, card = _make_card(self, app)
 
        tk.Label(card, text="Scan Your Cougar Card Below",
                 font=app.f_title, bg=BG_COLOR, fg="black",
                 wraplength=670, justify="center").place(relx = 0.5, y = 200, anchor="center")
 
        # animated wave icon
        self._wave_dark = ImageTk.PhotoImage(Image.open("Scan Card Wave Dark.png").resize((78, 29)))
        self._wave_light = ImageTk.PhotoImage(Image.open("Scan Card Wave Light.png").resize((78, 29)))
        
        self._wave_lbl = tk.Label(card, image=self._wave_dark, bg = BG_COLOR, bd=0)
        self._wave_lbl.place(x=393, y=413, anchor="center")
        self._animate(card)
        
        
        
        
        # start NFC polling in background
        self._polling = True
        self._thread  = threading.Thread(target=self._poll_nfc, args=(app,), daemon=True)
        self._thread.start()
    
    def _animate(self, card):
        current = self._wave_lbl.cget("image")
        if str(current) == str(self._wave_dark):
            self._wave_lbl.config(image=self._wave_light)
        else: 
            self._wave_lbl.config(image=self._wave_dark)
        self.after(700, lambda: self._animate(card))
    
    def _poll_nfc(self, app):
        available = readers()
        if not available:
            print("No NFC reader found.")
            return
 
        reader   = available[0]
        GET_UID  = [0xFF, 0xCA, 0x00, 0x00, 0x00]
        last_uid = None
        
        while self._polling:
            try: 
                connection = reader.createConnection()
                connection.connect()
                
                data, sw1, sw2 = connection.transmit(GET_UID)
                
                if sw1 == 0x90 and sw2 == 0x00:
                    UID = toHexString(data).replace(" ", "")
                    
                    if UID != last_uid: 
                        print(f"Card Detected! UID: {UID}")
                        last_uid = UID
                        self._polling = False
                        app.after(0, lambda u=UID: self._handle_uid(u, app))
            except NoCardException:
                last_uid = None # card removed, reset so next scan works 
            except CardConnectionException: 
                last_uid = None 
            
            time.sleep(0.5) # poll
    
    def _handle_uid(self, uid, app): 
        def work():
            row_num, row_data = find_row_by_uid(uid)
            
            try: 
                if row_num:
                    headers    = get_headers()
                    first_name = row_data[headers.index("First Name")]
                    points     = award_points(row_num, app.event_name)
     
                    if points is None:
                        app.after(0, app.show_already_in)
                    else:
                        msg = f"Welcome back,\n{first_name}!"
                        app.after(0, lambda: app.show_success(msg, points))
                else:
                    app.after(0, lambda: app.show_uhid_entry(uid))
                
            except Exception as e:
                print(f"[ERROR in _handle_uid]: {e}")  # <-- you'll now see what's failing
                import traceback; traceback.print_exc()
 
        threading.Thread(target=work, daemon=True).start()
    
    def destroy(self): 
        self._polling = False
        super().destroy()

class SuccessScreen(tk.Frame): 
    def __init__(self, master, message, points): 
        super().__init__(master, bg = BG_COLOR)
        app = master
        
        _, card = _make_card(self, app)
        
        tk.Label(card, 
                 text = f"{message} +{points} points awarded!",
                 font = app.f_title, 
                 bg = BG_COLOR, 
                 fg = "black", 
                 wraplength = 670, justify = "center").place(relx=.5,rely=.35,anchor="center")
        
        # circle checkmark 
        # c = tk.Canvas(card, width=90, height=90, bg=BG_COLOR, highlightthickness=0)
        # c.place(relx=0.5, rely=0.62, anchor="center")
        # c.create_oval(3, 3, 87, 87, fill=CHK_COLOR, outline="")
        # c.create_text(45, 45, text="✓", fill="white",
        #               font=tkfont.Font(family="Georgia", size=36, weight="bold"))
        
        self._chk_img = ImageTk.PhotoImage(Image.open("Check.png").resize((150, 150)))
        chk = tk.Label(card, image=self._chk_img, bg=BG_COLOR, bd=0)
        chk.place(relx=0.5, rely=0.62, anchor="center")
 
        # auto-return to scan after 3 s
        self.after(3000, app.show_scan)

class AlreadyInScreen(tk.Frame):
    def __init__(self, master): 
        super().__init__(master, bg=BG_COLOR)
        app = master
 
        _, card = _make_card(self, app)
 
        tk.Label(card, text="All good! You're already in!",
                 font=app.f_title, bg=BG_COLOR, fg="black",
                 wraplength=670, justify="center").place(relx=0.5, rely=0.35, anchor="center")
        
        self._thumb_img = ImageTk.PhotoImage(Image.open("Thumbs.png").resize((150,150)))
        thumb = tk.Label(card, image=self._thumb_img, bg=BG_COLOR, bd=0)
        thumb.place(relx=0.5, rely=0.62, anchor="center")
       
        
        # self._btn_img = ImageTk.PhotoImage(Image.open("Confirm_Button.png").resize((300,45)))
        
        # btn = tk.Label(self, image=self._btn_img, cursor = "hand2", bg=BG_COLOR, bd = 0)
        # btn.place(relx=0.5,y = SCREEN_H-100, anchor="center")
        # btn.bind("<Button-1>", lambda e: confirm())
 
        self.after(3000, app.show_scan)


class UHIDScreen(tk.Frame):
    def __init__(self, master): 
        super().__init__(master, bg=BG_COLOR)
        app = master
 
        _, card = _make_card(self, app)
 
        tk.Label(card, text="Enter your UH ID below:",
                 font=app.f_title, bg=BG_COLOR, fg="black",
                 wraplength=670, justify="center").place(relx=0.5, rely=0.32, anchor="center")
 
        self._entry_var = tk.StringVar()
        entry = tk.Entry(card, textvariable=self._entry_var,
                         font=app.f_sub, bg="#dedad1", fg="black",
                         bd=0, highlightthickness=1,
                         highlightbackground=CHK_COLOR, highlightcolor=CHK_COLOR,
                         insertbackground="black", justify="center")
        
        entry.place(relx=0.5, rely=0.50, anchor="center", width=220, height=38)
        entry.focus_set()
 
        self._err = tk.Label(card, text="", font=app.f_small,
                             bg=BG_COLOR, fg=X_COLOR)
        self._err.place(relx=0.5, rely=0.60, anchor="center")
        
       
        def submit(*_):
            uh_id = self._entry_var.get().strip()
            if not uh_id:
                return
            self._err.config(text="Searching...", fg = "black")
 
            def work():
                row_num, row_data = find_row_by_uhid(uh_id)
                if row_num:
                    headers    = get_headers()
                    first_name = row_data[headers.index("First Name")]
                    last_name  = row_data[headers.index("Last Name")]
                    app.after(0, lambda: app.show_confirm_identity(
                        first_name, last_name, row_num))
                else:
                    app.after(0, lambda: self._not_found(uh_id, app))
 
            threading.Thread(target=work, daemon=True).start()
        
        entry.bind("<Return>", submit)
 
        # btn = tk.Button(card, text="Submit", font=app.f_btn,
        #                 bg=CHK_COLOR, fg=BORDER,
        #                 activebackground=CHK_COLOR, activeforeground=CHK_COLOR,
        #                 bd=0, padx=16, pady=8, cursor="hand2",
        #                 command=submit)
        # btn.place(relx=0.5, rely=0.72, anchor="center")
        # entry.bind("<Return>", submit)
        
        self._btn_img = ImageTk.PhotoImage(Image.open("Submit Button.png").resize((300,45)))
        
        btn = tk.Label(self, image=self._btn_img, cursor = "hand2", bg=BG_COLOR, bd = 0)
        btn.place(relx=0.5,rely = 0.72, anchor="center")
        btn.bind("<Button-1>", lambda e: submit())
    
    def _not_found(self, uh_id, app):
        self._err.config(text=f"UH ID '{uh_id}' not found. Try again or continue to register.", fg = X_COLOR)
 
        def go_register():
            app.show_registration(app._current_uid, uh_id)
 
        # place on card
        for w in self.winfo_children():
            if isinstance(w, tk.Frame) and w.cget("bg") == BG_COLOR:
                # reg_btn2 = tk.Button(w, text="Register as new member →",
                #                      font=app.f_small, bg=CHK_COLOR, fg=CHK_COLOR,
                #                      activebackground=BORDER, bd=0,
                #                      padx=12, pady=6, cursor="hand2",
                #                      command=go_register)
                # reg_btn2.place(relx=0.5, rely=0.86, anchor="center")
                
                self._btn_img = ImageTk.PhotoImage(Image.open("Register_New.png").resize((300,45)))
                
                btn = tk.Label(self, image=self._btn_img, cursor = "hand2", bg=BG_COLOR, bd = 0)
                btn.place(relx=0.5,rely = 0.85, anchor="center")
                btn.bind("<Button-1>", lambda e: go_register())

class ConfirmScreen(tk.Frame):
    def __init__(self, master, first_name, last_name, row_num): 
        super().__init__(master, bg=BG_COLOR)
        app = master
        
        _, card = _make_card(self, app)
        
        tk.Label(card, text="Is this you?",
                 font=app.f_title, bg=BG_COLOR, fg="black").place(relx=0.5, rely=0.30, anchor="center")
        
        tk.Label(card, text=f"{first_name} {last_name}",
                 font=app.f_sub, bg=BG_COLOR, fg="black").place(relx=0.5, rely=0.44, anchor="center")
        
        # x button
        def deny():
            app.show_uhid_entry(app._current_uid)
        
        # ✓ button
        def confirm():
            def work():
                points = award_points(row_num, app.event_name)
                map_uid_to_row(row_num, app._current_uid)
                if points is None:
                    app.after(0, app.show_already_in)
                    return
                app.after(0, lambda: app.show_card_mapped(first_name, points))
                
            threading.Thread(target=work, daemon=True).start()
        
        btn_frame = tk.Frame(card, bg=BG_COLOR)
        btn_frame.place(relx=0.5, rely=0.62, anchor="center")
        
        self._x_img = ImageTk.PhotoImage(Image.open("X Button.png").resize((60,60)))
        x_btn = tk.Label(btn_frame, image=self._x_img, bg=BG_COLOR, bd =0, cursor = "hand2")
        x_btn.pack(side="left", padx=18)
        x_btn.bind("<Button-1>", lambda e: deny())
        
        self._chk_img = ImageTk.PhotoImage(Image.open("Yes Button.png").resize((60,60)))
        chk_btn = tk.Label(btn_frame, image=self._chk_img, bg=BG_COLOR, bd=0, cursor="hand2")
        chk_btn.pack(side='left', padx=18)
        chk_btn.bind("<Button-1>", lambda e: confirm())
        
        # btn = tk.Label(self, image=self._btn_img, cursor = "hand2", bg=BG_COLOR, bd = 0)
        # btn.place(relx=0.5,y = SCREEN_H-100, anchor="center")
        # btn.bind("<Button-1>", lambda e: confirm())
        
        # cross = tk.Canvas(btn_frame, width=52, height=52, bg=BG_COLOR, highlightthickness=0)
        # cross.pack(side="left", padx=18)
        # cross.create_oval(2, 2, 50, 50, fill=X_COLOR, outline="")
        # cross.create_text(26, 26, text="✕", fill=BG_COLOR,
        #                   font=tkfont.Font(family="Georgia", size=20, weight="bold"))
        # cross.bind("<Button-1>", lambda e: deny())
        
        # check = tk.Canvas(btn_frame, width=52, height=52, bg=BG_COLOR, highlightthickness=0)
        # check.pack(side="left", padx=18)
        # check.create_oval(2, 2, 50, 50, fill=CHK_COLOR, outline="")
        # check.create_text(26, 26, text="✓", fill=BG_COLOR,
        #                   font=tkfont.Font(family="Georgia", size=20, weight="bold"))
        # check.bind("<Button-1>", lambda e: confirm())

class RegistrationScreen(tk.Frame):
    def __init__(self, master, uid, uh_id): 
        super().__init__(master, bg=BG_COLOR)
        app = master
 
        _, card = _make_card(self, app)
 
        tk.Label(card, text="Please complete this registration.",
                 font=app.f_title, bg=BG_COLOR, fg="black",
                 wraplength=670, justify="center").place(relx=0.5, rely=0.18, anchor="center")
 
        # form fields
        # fields_frame = tk.Frame(card, bg=BG_COLOR)
        # fields_frame.place(relx=0.5, rely=0.32, anchor="n", width=340)
 
        def field(parent, label_text, lx, ly, fx, fy, fw):
            tk.Label(card, text=label_text, font=app.f_label,
                     bg=BG_COLOR, fg="black", anchor="w").place(x=lx,y=ly)
            e = tk.Entry(parent, font=app.f_sub,
                         bg=INPUT_BG, fg="black", bd=0,
                         highlightthickness=1,
                         highlightbackground=BORDER, highlightcolor=CHK_COLOR,
                         insertbackground="black")
            e.place(x=fx, y=fy, width = fw, height=23)
            return e
 
        # name_row = tk.Frame(fields_frame, bg=BG_COLOR)
        # name_row.pack(fill="x")
 
        # left = tk.Frame(name_row, bg=BG_COLOR)
        # left.pack(side="left", expand=True, fill="x", padx=(0, 6))
        first_entry = field(card, "First Name", lx=170, ly=170, fx=170, fy=197, fw=210)
 
        # right = tk.Frame(name_row, bg=BG_COLOR)
        # right.pack(side="left", expand=True, fill="x")
        last_entry  = field(card, "Last Name",  lx=450, ly=170, fx=450, fy=197, fw=210)
 
        email_entry = field(card, "Email",      lx=170, ly=238, fx=170, fy=265, fw=490)
 
        self._err = tk.Label(card, text="", font=app.f_small,
                             bg=BG_COLOR, fg=X_COLOR)
        self._err.place(relx=0.5, rely=0.80, anchor="center")
 
        tk.Label(card,
                 text="Please keep in mind this is only for point tracking.\n"
                      "To become an official member please visit our LinkTree for the form!",
                 font=app.f_small, bg=BG_COLOR, fg=DISCLAIMER,
                 wraplength=670, justify="center").place(relx=0.5, rely=0.88, anchor="center")
 
        def submit():
            first = first_entry.get().strip()
            last  = last_entry.get().strip()
            email = email_entry.get().strip()
 
            if not first or not last:
                self._err.config(text="First and last name required.")
                return
 
            self._err.config(text="Registering…", fg = DISCLAIMER)
 
            def work():
                row_num = create_new_row(uid, uh_id, first, last, email, app.event_name)
                points  = _points_for_event(app.event_name)
                msg = f"Welcome to SASE,\n{first}!"
                app.after(0, lambda: app.show_success(msg, points or 0))
 
            threading.Thread(target=work, daemon=True).start()
 
        # btn = tk.Button(card, text="Submit Registration →",
        #                 font=app.f_btn, bg=CHK_COLOR, fg=BORDER,
        #                 activebackground=BORDER, activeforeground=CHK_COLOR,
        #                 bd=0, padx=16, pady=9, cursor="hand2",
        #                 command=submit)
        # btn.place(relx=0.5, rely=0.70, anchor="center")
        
        self._btn_img = ImageTk.PhotoImage(Image.open("Submit Button.png").resize((300,45)))
        
        btn = tk.Label(self, image=self._btn_img, cursor = "hand2", bg=BG_COLOR, bd = 0)
        btn.place(relx=0.5,rely =0.72, anchor="center")
        btn.bind("<Button-1>", lambda e: submit())

# ============================================================================
#                                    Main
# ============================================================================
def main(): 
    # available_readers = readers()
    # if not available_readers:
    #     print("No readers found.")
    #     return 
    
    # print("Available Readers:")
    
    # for i, r in enumerate(available_readers):
    #     print(f"     [{i}] {r}")
    # print()
    
    # # Select event before starting!!! 
    # event_name = select_event()
    # if not event_name:
    #     return 
  
    # reader = available_readers[0]
    # nfc = NFC(event_name)
    
    # print("Ready! Waiting for NFC Card...")
    
    # # prevents double scanning ID
    # last_uid = None 
    
    # try: 
    #     while True: 
    #         try: 
    #             connection = reader.createConnection()
    #             connection.connect()
                
    #             data, sw1, sw2 = connection.transmit(GET_UID)
                
    #             if sw1 == 0x90 and sw2 == 0x00:
    #                 UID = toHexString(data).replace(" ", "")
                    
    #                 if UID != last_uid: 
    #                     print(f"Card Detected! UID: {UID}")
    #                     last_uid = UID
    #                     nfc.handle(UID)
    #         except NoCardException:
    #             last_uid = None # card removed, reset so next scan works 
    #         except CardConnectionException: 
    #             last_uid = None 
            
    #         time.sleep(0.5) # poll
    
            
    # except KeyboardInterrupt:
    #     print("\nStopped By User")
    
    app = App()
    app.mainloop()

if __name__ == "__main__":
    main()