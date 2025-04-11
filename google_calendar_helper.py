import streamlit as st
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from datetime import datetime, timedelta, timezone
import pytz
import dateutil.parser

SCOPES = ['https://www.googleapis.com/auth/calendar.events']

def authenticate_google():
    creds_dict = st.secrets["gcp_service_account"]
    creds = Credentials.from_service_account_info(dict(creds_dict), scopes=SCOPES)
    
    return build('calendar', 'v3', credentials=creds)

def convert_to_datetime(date_str, time_str):
    # If date_str is like 'Saturday' → get next Saturday
    weekdays = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]

    if date_str.lower() in weekdays:
        today = datetime.today()
        target_weekday = weekdays.index(date_str.lower())
        days_ahead = target_weekday - today.weekday()
        if days_ahead <= 0:
            days_ahead += 7
        date_obj = today + timedelta(days=days_ahead)
    else:
        # Otherwise assume it's already in YYYY-MM-DD format
        date_obj = datetime.fromisoformat(date_str)

    # Combine date and time and parse correctly
    full_datetime_str = f"{date_obj.date()} {time_str}"
    dt = dateutil.parser.parse(full_datetime_str)

    return dt

def check_time_conflict(date_str, time_str, duration_minutes=60):
    service = authenticate_google()

    start = convert_to_datetime(date_str, time_str)
    end = start + timedelta(minutes=duration_minutes)
    
    user_timezone = pytz.timezone(st.secrets.get("default_timezone", "UTC"))
    
    if start.tzinfo is None:
        start = user_timezone.localize(start)
    
    if end.tzinfo is None:
        end = user_timezone.localize(end)
    
    # Ensure start and end are in user's timezone for accurate comparison
    start = start.astimezone(user_timezone)
    end = end.astimezone(user_timezone)
    
    start_of_day = start.replace(hour=0, minute=0)
    end_of_day = start.replace(hour=23, minute=59)
    
    events_result = service.events().list(
        calendarId=st.secrets["calendar_id"],
        timeMin=start_of_day.isoformat(),
        timeMax=end_of_day.isoformat(),
        singleEvents=True,
        orderBy='startTime'
    ).execute()
    
    events = events_result.get('items', [])
    
    # Additional check for overlapping events
    for event in events:
        event_start = event['start'].get('dateTime')
        event_end = event['end'].get('dateTime')

        if event_start and event_end:
            event_start_dt = dateutil.parser.isoparse(event_start)
            event_end_dt = dateutil.parser.isoparse(event_end)
            
            # Force same timezone for correct comparison
            event_start_dt = event_start_dt.astimezone(user_timezone)
            event_end_dt = event_end_dt.astimezone(user_timezone)

            # Check if the new event overlaps with existing one
            if start < event_end_dt and end > event_start_dt:
                return True

    return False  # No conflict

def suggest_next_available_time(date_str, time_str, duration_minutes=60):
    service = authenticate_google()

    start_dt = convert_to_datetime(date_str, time_str)
    
    user_timezone = pytz.timezone(st.secrets.get("default_timezone", "UTC"))
    
    if start_dt.tzinfo is None:
        start_dt = user_timezone.localize(start_dt)
    
    start_dt = start_dt.astimezone(user_timezone)
    
    end_of_day = start_dt.replace(hour=23, minute=59)

    now = start_dt
    while now + timedelta(minutes=duration_minutes) <= end_of_day:
        slot_end = now + timedelta(minutes=duration_minutes)
        
        events_result = service.events().list(
            calendarId=st.secrets["calendar_id"],
            timeMin=now.isoformat(),
            timeMax=slot_end.isoformat(),
            singleEvents=True,
            orderBy='startTime'
        ).execute()
        
        events = events_result.get('items', [])

        conflict = False
        for event in events:
            event_start = event['start'].get('dateTime')
            event_end = event['end'].get('dateTime')

            if event_start and event_end:
                event_start_dt = dateutil.parser.isoparse(event_start)
                event_end_dt = dateutil.parser.isoparse(event_end)
                
                event_start_dt = event_start_dt.astimezone(user_timezone)
                event_end_dt = event_end_dt.astimezone(user_timezone)

                if now < event_end_dt and slot_end > event_start_dt:
                    conflict = True
                    break

        if not conflict:
            return now.strftime("%H:%M")

        now += timedelta(minutes=15)

    return None

def create_calendar_event(event_data, user_timezone, duration_minutes=60):
    service = authenticate_google()

    date_str = fix_past_date_if_needed(event_data['date'])
    start = convert_to_datetime(date_str, event_data['time'])
    end = start + timedelta(minutes=duration_minutes)
    
    timezone_obj = pytz.timezone(user_timezone)
    
    if start.tzinfo is None:
        start = timezone_obj.localize(start)
    if end.tzinfo is None:
        end = timezone_obj.localize(end)
    
    start = start.astimezone(timezone_obj)
    end = end.astimezone(timezone_obj)

    event = {
        'summary': event_data.get("title", "Scheduled Event"),
        'description': f"Created by SchedulAI for {', '.join(event_data.get('participants', []))}",
        'start': {
            'dateTime': start.isoformat(),
            'timeZone': user_timezone,
        },
        'end': {
            'dateTime': end.isoformat(),
            'timeZone': user_timezone,
        },
    }

    calendar_id = st.secrets["calendar_id"]

    return service.events().insert(calendarId=calendar_id, body=event).execute()

def fix_past_date_if_needed(date_str):
    """
    Receives a date in 'YYYY-MM-DD' format.
    If the date is in the past → assume next year.
    """
    today = datetime.today().date()
    extracted_date = datetime.fromisoformat(date_str).date()
    
    # If year in the past → replace with current year
    if extracted_date.year < today.year:
        extracted_date = extracted_date.replace(year=today.year)

    # If still in the past (already happened this year) → move to next year
    if extracted_date < today:
        extracted_date = extracted_date.replace(year=extracted_date.year + 1)
    
    return extracted_date.isoformat()