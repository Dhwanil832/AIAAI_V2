# AI-AAI V2: Agentic Accident Investigation & Reporting

AI-AAI V2 is the current development version of an **on-premise, agentic workplace-safety reporting system** for steel manufacturing environments.

The system is designed for settings where an incident report begins with incomplete information, multiple evidence sources may become available over time, and the application must decide what information is still needed before producing a structured record for review.

This repository extends the earlier AI-Assisted Accident Investigation system presented at **AISTech 2025** into a modular agentic workflow with local LLM inference, semantic retrieval, witness integration, and targeted visual evidence requests.

> **Scope:** AI-AAI V2 focuses on incident reporting, evidence collection, clarification, and review support.  
> The separate `Root_Cause_Analysis` project investigates deeper causal explanation, competing hypotheses, and progressive evidence-driven RCA.

---

## What the System Does

A reporter can describe an incident conversationally instead of completing a static form. The system then:

1. extracts only explicitly stated incident fields;
2. tracks which required information is still missing;
3. asks context-aware follow-up questions;
4. preserves the original conversational account alongside the structured report;
5. retrieves similar historical incidents;
6. requests additional evidence when it could materially improve the investigation;
7. incorporates witness accounts;
8. flags incomplete reports for review; and
9. supports an administrative review and approval workflow.

The system runs entirely on-premise with local model inference.

---

## Agentic Workflow

### Intake Agent
Maintains the reporting session, tracks incident type and required fields, preserves dialogue state, and determines the next missing information to request.

### Extraction Agent
Converts natural-language responses into structured incident fields while explicitly avoiding unsupported inference. Question context is used to correctly interpret short answers.

### Flagging Agent
Checks report completeness and identifies reports that require additional review because multiple required fields remain unresolved.

### Similarity Agent
Retrieves related historical incidents using semantic search through Qdrant, with a weighted field-based fallback when the vector index is unavailable.

### Witness Agent
Synthesizes the primary reporter account with additional witness statements while preserving contradictions rather than silently resolving them.

### Vision Reasoning Agent
Determines whether photographic evidence would materially help the investigation and, when warranted, asks the reporter for specific visual evidence.

### Corrective-Action Support
Surfaces recurring corrective actions from similar historical incidents as suggestions for human review rather than autonomous safety decisions.

---

## System Architecture

```text
Reporter / Admin
       |
       v
React + Vite Frontend
       |
       v
FastAPI Backend
       |
       +--> Intake / Extraction / Flagging
       |
       +--> Witness + Vision Reasoning
       |
       +--> Similarity Retrieval
       |       |
       |       +--> Qdrant
       |       +--> Historical Incident Store
       |
       +--> PostgreSQL
       +--> MinIO
       +--> Ollama
       +--> faster-whisper
```

### Core Stack

- **Local LLM inference:** Ollama
- **Backend:** FastAPI
- **Frontend:** React + Vite
- **Relational storage:** PostgreSQL
- **Semantic retrieval:** Qdrant
- **Object storage:** MinIO
- **Speech-to-text:** faster-whisper

No external cloud LLM API is required for the core workflow.

---

## Research Motivation

Industrial incident reporting is rarely a clean data-entry problem.

Reports may begin with:

- incomplete descriptions;
- short or ambiguous answers;
- missing fields;
- conflicting witness accounts;
- visual evidence that has not yet been requested;
- historical incidents that may provide useful context; and
- uncertainty about what information is still necessary.

AI-AAI V2 explores how an agentic reporting system can **maintain context, recognize information gaps, request useful evidence, and preserve uncertainty** instead of simply converting free text into a completed form.

The broader question is:

> **How should an AI system decide what information it still needs before it can produce a useful account of an incident?**

---

## Project Evolution

### AISTech 2025 System
The initial AI-Assisted Accident Investigation work focused on conversational reporting, context retention, structured information capture, and dynamic action sequencing.

### AI-AAI V2
The current system extends that foundation with:

- modular agent responsibilities;
- local LLM inference;
- semantic retrieval over historical incidents;
- contextual field extraction;
- witness-account synthesis;
- targeted visual-evidence requests;
- completeness-aware review support; and
- a full on-premise application stack.

This repository represents the **current system implementation**, not the exact code snapshot associated with the original AISTech 2025 paper.

---

## Repository Structure

```text
AIAAI_V2/
├── backend/
│   ├── agents/
│   │   ├── intake.py
│   │   ├── extractor.py
│   │   ├── flagging.py
│   │   ├── similarity.py
│   │   ├── witness.py
│   │   ├── vision_reasoning.py
│   │   └── corrective_actions.py
│   ├── core/
│   ├── models/
│   ├── routers/
│   ├── schemas/
│   ├── migrations/
│   └── scripts/
│
└── frontend/
    ├── src/
    │   ├── pages/
    │   ├── components/
    │   ├── api/
    │   └── context/
    └── public/
```

---

## Running the System

The application requires the following local services:

- PostgreSQL
- Ollama
- Qdrant
- MinIO
- FastAPI backend
- React/Vite frontend

Detailed installation and service-start instructions can be placed in:

```text
docs/SETUP.md
```

This keeps the main README focused on the research system while preserving full reproducibility instructions separately.

---

## Safety and Human Oversight

AI-AAI V2 is a research and decision-support system.

It is **not** intended to autonomously determine blame, establish an official root cause, or issue plant operating instructions. Generated summaries, retrieved incidents, requested evidence, and corrective-action suggestions remain subject to human review.

---

## Related Work

- **Progressive Evidence-Driven Root Cause Analysis**  
  Separate research project investigating competing causal explanations, active information seeking, evidence-grounded revision, and versioned RCA.

- **AI-Assisted Accident Investigation, AISTech 2025**  
  Earlier version of the conversational incident-reporting system that motivated the current architecture.

---

## Affiliation

Developed as part of research at the **Center for Innovation through Visualization and Simulation (CIVS), Purdue University Northwest**.
