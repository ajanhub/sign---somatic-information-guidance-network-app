# SIGN: Somatic Information Guidance Network

An application built for the **Congressional App Challenge** using Python and Streamlit.

**Creator:** Akhil Jangari *(Assisted by AI for documentation and styling)*

---

## Overview

I built **SIGN** as a lightweight, privacy-focused health and wellness platform in Python. The goal of this project is to give people an easy, self-contained tool to track their daily nutrition and safely evaluate symptoms before deciding whether they need to see a doctor.

> **Disclaimer:** SIGN is strictly educational. It is not a medical device, it never provides clinical diagnoses, and it should never replace an evaluation or care from a licensed healthcare provider.

---

## What the App Does

The application is broken into three main features:

### 1. Calories & Weight Tracker
- Estimates resting metabolism (BMR) and daily energy expenditure (TDEE) using the Mifflin-St Jeor formula based on personal metrics.
- Calculates personalized maintenance, deficit, or surplus caloric targets with built-in safety minimums.
- Logs daily meals with full macronutrient breakdowns (protein, carbs, and fats) and tracks weight progress over time with trend lines.

### 2. Symptom Evaluation
- Guides users through a structured symptom questionnaire with plain-English definitions for complex medical body regions.
- Uses strict, deterministic decision trees to assign an appropriate care tier: **Emergency**, **Urgent Care**, **Primary Care**, or **Self-Care**.
- Immediately flags dangerous warning signs or crisis language on screen.
- Generates a downloadable **Appointment Preparation Summary (.txt)** that users can print or take directly to their doctor.

### 3. Emergency Directory
- Quick-dial access to essential emergency resources (911, 988 Suicide & Crisis Lifeline, and Poison Control).
- Direct location search links to find nearby emergency rooms, urgent care centers, and pharmacies.

---

## How to Run It Locally

### Requirements
- Python 3.10+
- `streamlit>=1.40`
- `requests>=2.31`

### Setup & Launch

1. Clone or download this project to your computer.
2. Open your terminal or Command Prompt in the project folder and install the dependencies/requirements with pip install -r requirements.txt
3. Navigate into the folder of the script and run cd (space) the pathway
4. Lastly, run the app with py -m streamlit run app2.py
