# Customer AI chat

The public storefront calls `POST /ai/chat`. This uses the OpenRouter intent router,
tenant-scoped tools, and OpenRouter response generator. Older helpers in `intent.py`
and the legacy symptom questionnaires are not the normal public chat path.

## Request flow

1. Authorize the customer session and pharmacy, then load up to 24 recent user/AI
   messages. Internal state and other customers' messages are not sent to the model.
2. Return immediate guidance for detected emergency warning signs without waiting
   for an external model. A session already handed to a pharmacist remains a human conversation.
3. Classify the latest request with conversation history through OpenRouter. If the
   configured router fails, try the main model before using the outage heuristic.
4. Retrieve current pharmacy data for stock, prices, products, and store information.
   Ordinary health questions use `HEALTH_GUIDANCE` and do not require a pharmacy document.
5. Generate a natural response through OpenRouter with the same history, current
   tool data, and permitted workflow actions. Main-model failures use the fallback model.
6. Return only backend-selected buttons and citations. Text cannot open a prescription
   uploader, invent a medicine ID, submit an order, or claim an appointment was booked.

## Boundaries

The assistant can explain general health information and ask relevant questions. It
must not diagnose, prescribe, select a treatment for a patient, or give individualized
doses. Persistent symptoms, medicine suitability, children, pregnancy, interactions,
and uncertain cases should be referred to a pharmacist/clinician. Emergencies need
immediate medical care, not a wait for a pharmacy reply.

Pharmacy-specific facts must come from current tool data. Conversation history provides
context, not authoritative stock or prices. Missing pharmacy facts should be identified
specifically. If models fail, verified operational information can still be shown;
otherwise the assistant reports temporary unavailability.

Prescription uploads belong to checkout and pharmacist review. Appointment booking uses
its own form and never requires prescription upload. A proposed action is not a completed action.

## Configuration and verification

Docker/Render use `AI_PROVIDER=openrouter`, `OPENROUTER_API_KEY`, and router/main/fallback
model settings. The default router is `openai/gpt-4o-mini`; the previous Gemini 2.0
Flash endpoint returned HTTP 404 during verification. JSON mode and sufficient response
tokens are enabled for classification and generation. Model failures log model name,
error type, and router HTTP status without logging credentials or patient prompts.

Run `python -m pytest backend/tests -q` from the repository environment and `npm run build`
in `frontend`. Regression tests cover insomnia, follow-up history, customer isolation,
booking after health discussion, rejected model actions, emergency fallback, and model outages.
Synthetic real OpenRouter checks also covered insomnia, a three-night follow-up, and booking.

This is a demo assistant, not a clinically validated pharmacist replacement. Model quality
and availability can vary. History is bounded and the existing inactivity timeout still applies.
