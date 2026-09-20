# Walkthrough: prompt-pills-onboarding

## 1. Run the live example

```
cd components/python/prompt-pills-onboarding && python3 example.py
```

A how-to card for an increment-2 room with four buttons, the W2 pill hidden, the first-time hint, and the guide's six command rows.

## 2. Copy the file and describe your bot

```
cp onboarding.py /path/to/your-service/
```

Build a `Bot` with your name, the three things to know, the pills (label, command, category, tier, roles needed), the five steps, the roles and the "never" sentence. `EXAMPLE` is the shape.

## 3. Post the card and handle the buttons

Post `welcome_card(...)` right after your incident card and on `help`. A button submits `{"bot": "command", "text": ...}`; run it as if the person typed it.

## 4. The hint and the guide

Send `first_time_hint(name)` once per person per room; serve `guide_html()` at a help route.

## 5. Prove it

```
python3 -m unittest discover -s tests -t . -v
```
