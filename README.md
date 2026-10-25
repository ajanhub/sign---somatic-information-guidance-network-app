# sign---somatic-information-guidance-network-app
An app built by me for the Congressional App Challenge using Python script.
SIGN - Somatic Information Guidance Network

Built by Akhil Jangari (I used AI to assist with creating this README)

I built SIGN as a lightweight, privacy-focused health and wellness platform in Python. The goal of this project is to give people an easy, self-contained tool to track their nutrition and evaluate symptoms safely before deciding whether they need to see a doctor.

Disclaimer: SIGN is strictly educational. It is not a medical device, it never provides clinical diagnoses, and it should never replace an evaluation by a licensed healthcare provider.

What the App Does

The application is broken into three main features:

Calories & Weight Tracker

Estimates resting metabolism (BMR) and daily energy expenditure (TDEE) using the Mifflin-St Jeor formula based on personal metrics.

Calculates personalized maintenance, deficit, or surplus caloric targets.

Logs daily meals with macro breakdowns (protein, carbs, and fats) and tracks weight progress over time with trend lines.

Symptom Evaluation

Guides users through a structured symptom questionnaire with plain-English definitions for body regions.

Uses strict, rule-based decision trees to assign a care tier: Emergency, Urgent Care, Primary Care, or Self-Care.

Immediately flags dangerous symptoms or crisis language.

Generates a downloadable Appointment Preparation Summary (.txt) that users can print or take directly to their doctor.

Emergency Directory

Quick-dial access to essential resources (911, 988 Suicide & Crisis Lifeline, and Poison Control).

Direct location search links to find nearby emergency rooms, urgent care centers, and pharmacies.

How to Run It Locally

Requirements

Python 3.10+
streamlit>=1.40
requests>=2.31

Setup & Launch

Clone or download this project to your computer.

Open your terminal or Command Prompt in the project folder and run:

# Optional: Set up and activate a virtual environment
python -m venv .venv
# On Windows: .venv\Scripts\activate
# On macOS/Linux: source .venv/bin/activate


# Start the application
streamlit run app.py
