import streamlit as st
import json
import re
import pytz
import openai
from openai import OpenAI
from datetime import datetime
from google_calendar_helper import (
    create_calendar_event,
    check_time_conflict,
    suggest_next_available_time,
    fix_past_date_if_needed
)

# Set up OpenAI API
openai.api_key = st.secrets['OPENAI_API_KEY']
client = OpenAI()

# Set up Streamlit UI
st.set_page_config(page_title="SchedulAI", page_icon="📅")
st.title("📅 SchedulAI")

st.markdown("""
    SchedulAI es un asistente impulsado por inteligencia artificial que te ayuda a programar reuniones y 
    tareas en Google Calendar de manera fácil, como lo haría un asistente humano.""")

col1, col2 = st.columns([3, 2])

with col2:
    st.markdown("""
    ### Cómo funciona
    1. Escribe tu solicitud en lenguaje natural (por ejemplo: "Agenda una reunión con Juan mañana a las 15:00").
    2. La inteligencia artificial interpreta tu solicitud y extrae los detalles del evento.
    3. La aplicación verifica la disponibilidad en tu calendario de Google.
    4. Si el horario solicitado está disponible, el evento se crea directamente en tu calendario de Google.
    5. Si hay un conflicto, la aplicación sugiere el siguiente horario disponible para ese mismo día.
    """)

with col1:

    # User input
    user_prompt = st.text_area("Tu solicitud", placeholder="por ej. Agenda una reunión con Juan mañana a las 15:00")
    duration = st.number_input("⏱️ Duración del evento (minutos)", min_value=15, max_value=240, step=15, value=60)
    
    timezones = pytz.all_timezones
    default_timezone = st.secrets.get("default_timezone", "UTC")
    timezone = st.selectbox("Selecciona tu zona horaria:", timezones, index=timezones.index(default_timezone))

    if "event_data" not in st.session_state:
        st.session_state.event_data = None
    
    if st.button("Interpretar solicitud") and user_prompt:
        with st.spinner("Preguntando a IA..."):
            try:
                today_date = datetime.today().strftime("%Y-%m-%d")
                system_instruction = (
                    "You are an AI assistant that extracts event details from natural language scheduling requests. "
                    f"Today is {today_date}. "
                    "Return only a valid JSON object with the following fields: "
                    "`event_type`, `title`, `date`, `time`, `participants`. "
                    "Do not include any explanation, comments, or formatting like ```json. "
                    "If any detail is missing, infer it. Output only the pure JSON."
                    "If the user specifies a day of the week (like Monday), use the next occurrence of that day after today."
                )

                response = client.chat.completions.create(
                    model="gpt-4o",
                    messages=[
                        {"role": "system", "content": system_instruction},
                        {"role": "user", "content": user_prompt}
                    ],
                    temperature=0.2,
                    max_tokens=300
                )

                content = response.choices[0].message.content
                
                # Remove Markdown-style code block (```json ... ```)
                cleaned = re.sub(r"```(?:json)?\\s*([\\s\\S]*?)\\s*```", r"\1", content).strip()
                event_data = json.loads(cleaned)
                # Apply date correction
                event_data['date'] = fix_past_date_if_needed(event_data['date'])
                    
                st.success("✅ Evento interpretado exitosamente!")
                st.json(event_data)
                    
                st.session_state.event_data = event_data
                
            except Exception as e:
                    st.error("❌ Error interpretando solicitud: {e}")                  
              
      
    # Create or suggest new time if conflict exists
    if st.session_state.event_data:             
        if st.button("📆 Agendar en calendario de Google"):
            with st.spinner("Chequeando disponibilidad..."):
                try:
                    date = st.session_state.event_data["date"]
                    time = st.session_state.event_data["time"]
                
                    conflict = check_time_conflict(date, time, duration)
                    
                    if conflict:
                        st.warning("⚠️ Ese horario ya está ocupado.")
                        suggested_time = suggest_next_available_time(date, time, duration)
                        
                        if suggested_time:
                            st.info(f"Próximo horario disponible sugerido: **{suggested_time}**")
                                                            
                        else:
                            st.error("😕 No se encontraron horarios disponibles para ese día.")

                    else:
                        result = create_calendar_event(st.session_state.event_data, timezone, duration)
                        st.success("✅ Evento creado en calendario de Google!")
                        st.markdown(f"[View in Google Calendar]({result.get('htmlLink')})")

                except Exception as e:
                    st.error(f"❌ No se pudo crear el eventot: {e}")