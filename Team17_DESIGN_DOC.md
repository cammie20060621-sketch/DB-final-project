# Team17 Design Document — TransitFlow

## Section 1 — Entity-Relationship Diagram

## Section 2 — Normalisation Justification

## Section 3 — Graph Database Design Rationale

## Section 4 — Vector / RAG Design

## Section 5 — AI Tool Usage Evidence

### Example 1 — Relational Schema Design

**Context:**  
We needed to design the PostgreSQL relational schema for TransitFlow. The schema had to support metro stations, national rail stations, schedules, schedule stops, national rail bookings, seat layouts, fare classes, payments, feedback, and policy documents.

**Prompt:**  
Can you help us design a PostgreSQL schema for TransitFlow? We need to support metro schedules, national rail bookings, seat layouts, fare classes, payments, feedback, and policy documents.

**Outcome:**  
The AI helped us identify that schedule stops should be stored in separate junction tables instead of array columns inside the schedule tables. Based on this suggestion, we created `metro_schedule_stops` and `national_rail_schedule_stops`. This improved normalisation because each stop can reference a valid station through a foreign key, and the stop order can be queried directly using `stop_order`.

---

### Example 2— PostgreSQL seeding debugging

**Context:**  
During seeding, several mock JSON fields did not exactly match our schema column names.

**Prompt:**  
"Why does seed_postgres.py fail when inserting metro schedules, and how should first_train_time, last_train_time, and per_stop_rate_usd map to the schema?"

**Outcome:**  
The AI helped us map `first_train_time` to `departure_time`, `last_train_time` to `arrival_time`, and `per_stop_rate_usd` to `per_stop_fare_usd`. After updating the seed script, PostgreSQL seeding completed successfully.
---

### Example 3 — Mapping Mock JSON Data to the Schema

**Context:**  
When implementing `seed_postgres.py`, we found that some mock JSON field names did not exactly match our schema column names. For example, the JSON files used fields such as `first_train_time`, `last_train_time`, and `per_stop_rate_usd`.

**Prompt:**  
How should I map the fields in `metro_schedules.json` and `national_rail_schedules.json` to my PostgreSQL schema?

**Outcome:**  
The AI helped us map the JSON fields to the schema fields. For example, `first_train_time` was mapped to `departure_time`, `last_train_time` was mapped to `arrival_time`, and `per_stop_rate_usd` was mapped to `per_stop_fare_usd`. This helped us update the seeding script so that the schedule data could be inserted into PostgreSQL successfully.

---

### Example 6 — Testing Docker, PostgreSQL, Neo4j, and pgvector

**Context:**  
Before submission, we needed to confirm that the full TransitFlow system could run correctly, including Docker containers, PostgreSQL seeding, Neo4j graph seeding, pgvector policy documents, Ollama embeddings, and the Gradio UI.

**Prompt:**  
How can I verify that the whole TransitFlow database system is running correctly, including Docker, PostgreSQL, Neo4j, Ollama, and pgvector?

**Outcome:**  
The AI helped us organise a step-by-step testing workflow. We first checked `docker compose ps`, then ran `python skeleton/seed_postgres.py`, `python skeleton/seed_neo4j.py`, and `python skeleton/seed_vectors.py`. We also used pgAdmin to inspect PostgreSQL tables, Neo4j Browser to visualise graph relationships, and the Gradio debug panel to check which tools were called. This process helped us verify that each database component was running and connected to the UI.

## Section 6 — Reflection & Trade-offs
One important design decision was to separate schedule stops into junction tables instead of storing stop arrays in the schedule tables. This made the schema more normalised and allowed us to enforce foreign key constraints on each station in a route.

A second design decision was to use Neo4j for routing instead of implementing route search entirely in PostgreSQL. Although station and schedule data can be stored relationally, routing queries such as shortest path and alternative routes are easier to express and maintain using graph traversal algorithms.

In a production system, we would improve secret management and deployment. Database passwords and model provider keys should not be hardcoded or stored in plain `.env` files on local machines. We would use a managed secrets service, database migrations, connection pooling, and stronger monitoring for failed bookings or partial transaction errors.
