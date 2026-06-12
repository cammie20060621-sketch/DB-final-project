# IM2002 — Student Guide: Design Document Evaluation ·
## Section 1 - Entity-Relationship Diagram ·
![ER Diagram](ERD.png)


# Transportation Ticketing System — Database Schema Specification

This document defines the database tables, Primary Keys (PK), Foreign Keys (FK), and business logic relationships across the four core modules of the system.

---

## 1. Core Users & Transactions
This module handles user registration, ticket transactions, payment logs, and post-trip feedback.

###  `registered_users`
* **Key Fields**:
    * `user_id` (PK): Unique identifier for each user.
* **Relationships**: Referenced by multiple tables. A single user can have multiple travel history records (`metro_travel_history`), multiple reservations (`bookings`), multiple payments (`payments`), and multiple feedback entries (`feedback`).

###  `bookings`
* **Key Fields**:
    * `booking_id` (PK): Unique identifier for each booking.
    * `user_id` (FK): Links to `registered_users.user_id` (identifies which user made the booking).
    * `schedule_id` (FK): Links to `national_rail_schedules.schedule_id` (identifies the specific rail schedule).
    * `ticket_type` (FK): Links to `ticket_types.ticket_type` (identifies the ticket category used).
    * `layout_id`, `coach`, `seat_id` (FK): Composite foreign keys linking to the seating system to ensure the reserved seat physically exists on the train.

###  `payments`
* **Key Fields**:
    * `payment_id` (PK): Unique identifier for each payment.
    * `user_id` (FK): Links to `registered_users.user_id`.
    * `booking_id` (FK, Nullable): Links to `bookings.booking_id` (populated if the payment is for a national rail ticket).
    * `trip_id` (FK, Nullable): Links to `metro_travel_history.trip_id` (populated if the payment is for a metro fare deduction).

###  `feedback`
* **Key Fields**:
    * `feedback_id` (PK): Unique identifier for each feedback entry.
    * `user_id` (FK): Links to `registered_users.user_id` (identifies the passenger providing feedback).
    * `booking_id` (FK): Links to `bookings.booking_id` (associates the feedback with a specific booking).

---

## 2. Metro System
Handles urban transit/metro stations, standard schedules, and passenger tap-in/tap-out travel logs.

###  `metro_stations`
* **Key Fields**:
    * `station_id` (PK): Unique identifier for each metro station.
* **Relationships**: Referenced by schedule timetables (`metro_schedule_stops`) and passenger travel logs (`metro_travel_history`).

###  `metro_schedules
* **Key Fields**:
    * `schedule_id` (PK): Unique identifier for each metro schedule.

###  `metro_schedule_stops`
* **Key Fields**:
    * `schedule_id` (PK, FK): Links to `metro_schedules.schedule_id`.
    * `station_id` (PK, FK): Links to `metro_stations.station_id`.

###  `metro_travel_history`
* **Key Fields**:
    * `trip_id` (PK): Unique identifier for each travel record.
    * `user_id` (FK): Links to `registered_users.user_id` (identifies the commuter).
    * `schedule_id` (FK): Links to `metro_schedules.schedule_id` (identifies the train taken).
    * `entry_station_id` (FK): Links to `metro_stations.station_id` (the tap-in station).
    * `exit_station_id` (FK): Links to `metro_stations.station_id` (the tap-out station).

---

## 3. National Rail & Seats
Manages intercity, long-distance rail schedules, coach configurations, and fine-grained seat-level allocation systems.

###  `national_rail_stations`
* **Key Fields**:
    * `station_id` (PK): Unique identifier for each national rail station.

###  `national_rail_schedules`
* **Key Fields**:
    * `schedule_id` (PK): Unique identifier for each national rail schedule.

###  `national_rail_schedule_stops`
* **Key Fields**:
    * `schedule_id` (PK, FK): Links to `national_rail_schedules.schedule_id`.
    * `station_id` (PK, FK): Links to `national_rail_stations.station_id`.

###  `national_rail_coaches` & `national_rail_seat_layouts` & `national_rail_seats`
* **Core Business Logic**: 
    * These tables are interconnected via `layout_id` and `coach` to define which train models contain which coaches, and the exact seat layout (e.g., 1A, 1B) within each coach (`national_rail_seats`).
    * Ultimately, the `seat_id`, `coach`, and `layout_id` fields in the `bookings` table map to this module as FKs, preventing ghost bookings or double-booking errors.

---

## 4. Policies & Rules (Look-up Tables)
This module serves as the administrative backend control panel and strategy engine, primarily used for data validation, compliance check, and dynamic fare calculations.

###  `ticket_types`
* **Key Fields**:
    * `ticket_type` (PK): e.g., `ADULT`, `CONCESSION`, `STUDENT`.
* **Relationships**: Widely referenced as an FK by fare rule matrices (`ticket_type_rules`), cancellation policies (`refund_policy`), and transaction logs.

###  `refund_policy` & `refund_policy_windows`
* **Core Business Logic**: 
    * The primary key for `refund_policy` is `refund_policy_id`.
    * `refund_policy_windows` links back to the parent table via the `refund_policy_id` FK.
    * **One-to-Many Relationship**: This structure implements a tiered fee schedule (e.g., "Cancel X hours before departure to incur a Y% processing fee").

###  Static Controls & Legal Documentation Tables
* `booking_rules`: Governs limits such as maximum tickets per purchase or advance booking windows.
* `travel_policies`: Enforces operational guidelines regarding pets, oversized luggage, etc.
* `policy_documents`: Stores text assets like privacy policies and terms of service for frontend rendering.
* **Core Function**: These tables store system parameters, legal clauses, or algorithmic variables (such as `pricing_model` or `formula`) utilized by the backend API to dynamically compute distance-based or zone-based fares.

---
This document provides a concise breakdown of the **1:1 (One-to-One)**, **1:N (One-to-Many)**, and **M:N (Many-to-Many)** relationships for each table in the schema shown in "Untitled.jpg".
---

## 1. Core Users & Bookings

### `registered_users`
* **1:N Relationship:** To `bookings`, `metro_travel_history`, `payments`, and `feedback` (A single user can have multiple bookings, transit trips, payment transactions, and feedback records).

### `bookings`
* **1:N Relationship:** To `payments` and `feedback` (A single booking can trigger multiple payment attempts or correspond to multiple feedback responses).
* **M:N Junction:** Acts as the bridge connecting `registered_users` (M) and `national_rail_schedules` (N).

### `payments`
* **1:N "Many" Side:** Belongs to `registered_users` and `bookings`.

### `feedback`
* **1:N "Many" Side:** Belongs to `registered_users`, `bookings`, and `metro_travel_history`.

---

## 2. Tickets & Policies

### `ticket_types`
* **1:N Relationship:** To `bookings`, `metro_travel_history`, and `refund_policy`.

### `ticket_type_rules`
* **1:1 Relationship:** To `ticket_types` (Under a specific transport network, one ticket type maps to exactly one detailed pricing rule).

### `refund_policy`
* **1:N Relationship:** To `refund_policy_windows` (A single refund policy defines multiple refund percentage windows based on time frames).

### `refund_policy_windows`
* **1:N "Many" Side:** Belongs to `refund_policy`.

---

## 3. Metro System

### `metro_travel_history`
* **1:N Relationship:** To `feedback`.

### `metro_stations`
* **1:N Relationship:** To `metro_travel_history` (Acts as the entry station or exit station for multiple trips).
* **M:N Bridge End:** Shares a many-to-many relationship with `metro_schedules`, implemented via `metro_schedule_steps`.

### `metro_schedules`
* **1:N Relationship:** To `metro_travel_history`.
* **M:N Bridge End:** Shares a many-to-many relationship with `metro_stations`, implemented via `metro_schedule_steps`.

### `metro_schedule_steps`
* **M:N Junction Table:** Resolves the many-to-many relationship between `metro_schedules` (M) and `metro_stations` (N).

---

## 4. National Rail System

### `national_rail_stations`
* **M:N Bridge End:** Shares a many-to-many relationship with `national_rail_schedules`, implemented via `national_rail_schedule_stops`.

### `national_rail_schedules`
* **1:1 Relationship:** To `national_rail_seat_layouts` (A specific train schedule is bound to exactly one seat layout configuration).
* **1:N Relationship:** To `bookings` and `national_rail_fare_classes` (A schedule handles multiple bookings and hosts multiple fare pricing classes).
* **M:N Bridge End:** Shares a many-to-many relationship with `national_rail_stations`, implemented via `national_rail_schedule_stops`.

### `national_rail_schedule_stops`
* **M:N Junction Table:** Resolves the many-to-many relationship between `national_rail_schedules` (M) and `national_rail_stations` (N).

### `national_rail_fare_classes`
* **1:N "Many" Side:** Belongs to `national_rail_schedules`.

### `national_rail_seat_layouts`
* **1:1 Relationship:** To `national_rail_schedules`.
* **1:N Relationship:** To `national_rail_coaches` (A single layout comprises multiple coaches).

### `national_rail_coaches`
* **1:N Relationship:** To `national_rail_seats` (A single coach contains multiple specific seats).

### `national_rail_seats`
* **1:N "Many" Side:** Belongs to `national_rail_coaches`.

---
*Note: `travel_policies`, `booking_rules`, and `policy_documents` operate as independent configuration or content tables within this schema and do not have direct hardcoded relationship lines.*

---

## 3. 捷運系統 (Metro)

### `metro_travel_history` (捷運搭乘歷史)
* **1:N 關係：** 對 `feedback`。

### `metro_stations` (捷運車站)
* **1:N 關係：** 對 `metro_travel_history`（分別作為旅客的進站與出站）。
* **M:N 橋樑端：** 與 `metro_schedules` 構成多對多，透過 `metro_schedule_steps` 實作。

### `metro_schedules` (捷運班表)
* **1:N 關係：** 對 `metro_travel_history`。
* **M:N 橋樑端：** 與 `metro_stations` 構成多對多，透過 `metro_schedule_steps` 實作。

### `metro_schedule_steps` (捷運班表停靠站)
* **M:N 中間表：** 負責處理 `metro_schedules` (M) 與 `metro_stations` (N) 的多對多關係。

---

## 4. 國家鐵路系統 (National Rail)

### `national_rail_stations` (鐵路車站)
* **M:N 橋樑端：** 與 `national_rail_schedules` 構成多對多，透過 `national_rail_schedule_stops` 實作。

### `national_rail_schedules` (鐵路班表)
* **1:1 關係：** 對 `national_rail_seat_layouts`（一個班次固定一種座位佈局）。
* **1:N 關係：** 對 `bookings`、`national_rail_fare_classes`（一個班次有多個票價等級）。
* **M:N 橋樑端：** 與 `national_rail_stations` 構成多對多，透過 `national_rail_schedule_stops` 實作。

### `national_rail_schedule_stops` (鐵路停靠站)
* **M:N 中間表：** 負責處理 `national_rail_schedules` (M) 與 `national_rail_stations` (N) 的多對多關係。

### `national_rail_fare_classes` (鐵路票價等級)
* **1:N 的「多」端：** 隸屬於 `national_rail_schedules`。

### `national_rail_seat_layouts` (座位佈局)
* **1:1 關係：** 對 `national_rail_schedules`。
* **1:N 關係：** 對 `national_rail_coaches`（一種佈局包含多個車廂）。

### `national_rail_coaches` (鐵路車廂)
* **1:N 關係：** 對 `national_rail_seats`（一個車廂包含多個座位）。

### `national_rail_seats` (鐵路座位)
* **1:N 的「多」端：** 隸屬於 `national_rail_coaches`。

## Section 2 — Normalisation Justification

This section delves into the core database design choices for the TransitFlow system. It covers the rationale behind our Third Normal Form (3NF) relational database schema, the deliberate denormalization trade-offs made to optimize performance in real-world business contexts, and the cryptographic password hashing architecture implemented to safeguard user account data.

---

## 1. Normalisation to 3NF: Design Decisions & Theoretical Implementation

In the TransitFlow system, the scheduling architecture for train trips and their corresponding stops (as seen in `metro_schedules.json` and `national_rail_schedules.json`) represents a textbook application of Third Normal Form (3NF). We explicitly rejected the denormalized approach of storing stop sequences as an array within a single field. Instead, we isolated this data into an independent associative table named `schedule_stops` (the schedule stop junction table).

### Functional Dependency (FD) Analysis
* **1NF (First Normal Form) Compliance:** Let `schedule_id` be the unique identifier for a trip schedule, and `station_id` be the unique identifier for a station. If an array field were used to cram all stops into the primary schedule table, it would introduce non-atomic values, violating 1NF. Breaking them out into distinct rows guarantees that every attribute contains only atomic values.
* **2NF (Second Normal Form) Compliance:** In the `schedule_stops` table, the Composite Primary Key is defined as `(schedule_id, station_id)`. Within this structure, non-key attributes such as `arrival_time` and `stop_order` are **fully functionally dependent** on the entire composite primary key. There are no partial dependencies where an attribute relies on only a subset of the key. Eliminating partial dependencies satisfies 2NF.
* **3NF (Third Normal Form) Compliance:** No transitive dependencies exist among the non-key attributes. For instance, `arrival_time` is determined strictly by the combination of schedule and station; it is not transitively determined through any other non-key fields. Every non-key attribute depends directly on the key—adhering to the classic relational database golden rule: "*Depend on the key, the whole key, and nothing but the key*." This fulfills 3NF.

### Advantages of the Design Decision
This 3NF junction table design effectively eliminates Update Anomalies. For example, if a specific station's arrival time requires a minor adjustment, the system only needs to update a single row within `schedule_stops`. It completely bypasses the need to parse, reconstruct, or rewrite an entire complex array, ensuring strict data integrity and high query precision.

---

## 2. Denormalization Trade-offs & Performance Optimization

While 3NF guarantees data consistency, certain real-world business scenarios in TransitFlow demand a departure from rigid normalization. To maximize throughput for high-frequency queries and minimize development complexity, we introduced a deliberate denormalization compromise within the **Transaction and Payment Modules**.

### Concrete Compromise Case: Attribute Redundancy in `payments`
In a strictly normalized 3NF schema, a ticket transaction recorded in the `bookings` table already maintains the total order price (`amount_usd`). When a user completes a transaction, the corresponding record in the `payments` table theoretically only requires a foreign key (`booking_id`) referencing the booking table—storing the amount again is redundant.

### Rationale for Intentional Partial Normalization (Performance & Audit Capabilities)

| Consideration | 3NF Disadvantages | Denormalized (Redundant Amount) Advantages |
| :--- | :--- | :--- |
| **Query Performance** | Whenever financial systems reconcile accounts or pull transaction ledgers, expensive `JOIN` operations must be executed. Under millions of rows of transaction volume, this heavily degrades database performance. | The `payments` table retains its own amount data, allowing for high-throughput, single-table scans during queries, significantly reducing database I/O and CPU overhead. |
| **Data Snapshot & Audit Trail** | If historical bookings are later altered due to business adjustments (e.g., refunds, policy updates, or accidental system deletions), the historical truth of the actual "amount paid" is lost forever. | The amount field in the payment table acts as an immutable immutable "historical snapshot." Once written, it cannot be changed, ensuring the strict accuracy required for enterprise-grade financial audits and account reconciliation. |

---

## 3. Cryptographic Password Hashing Safety Design

When handling sensitive user data in `registered_users.json`, TransitFlow strictly prohibits the storage of passwords in plaintext. To counter modern security threats, we have abandoned obsolete hashing algorithms in favor of a contemporary cryptographic defense architecture.

### Why Legacy Algorithms Like MD5, SHA-1, and SHA-256 Were Rejected
Legacy algorithms like **MD5** and **SHA-1** have long been broken due to severe hash collision vulnerabilities and must never be used to secure passwords. More importantly, MD5, SHA-1, and even **SHA-256** are fundamentally classified as **general-purpose fast hashing algorithms** (engineered to quickly verify large files). 

This design characteristics implies that an attacker utilizing modern consumer-grade GPUs (Graphics Processing Units) or specialized ASIC hardware can execute billions of hash computations per second. If the database were leaked, an attacker could quickly reverse user passwords via brute-force or precomputed lookup attacks.

### Implemented Algorithms: Argon2id / bcrypt
This system universally implements **Argon2id** (or **bcrypt**, depending on team environment configurations) for password hashing:
* **Key Stretching:** These specialized algorithms execute tens of thousands of internal iterative loops, intentionally extending the calculation time of a single hash (targeting approximately 100 milliseconds per validation). This overhead is imperceptible to a legitimate user logging in, but it increases the computational cost of a brute-force attack by millions of fold.
* **Work Factor / Cost Factor:** The algorithms allow developers to adjust parameters (such as bcrypt's cost or Argon2id's memory and time dimensions). As computational hardware evolves over time, the team can scale up the work factor to counter increasing hardware speeds without changing the underlying codebase architecture.
* **Memory-Hard Behavior (Exclusive to Argon2id):** Argon2id requires a specific, configurable memory allocation during computation. This effectively thwarts hardware-accelerated cracking because massive parallel processing setups like GPUs hit a bottleneck due to restricted memory bandwidth per core, rendering massive parallel brute-forcing unfeasible.

### Salt Mechanics & Defeating Rainbow Table Attacks
A "Rainbow Table" is a massive, precomputed dictionary of common passwords (e.g., `123456`, `password`) matched against their corresponding hash values. If two users share identical passwords, their resulting hashes would match in a typical setup, enabling an attacker to instantly compromise accounts by looking up the leaked hash string.

To entirely eliminate this vulnerability, our system introduces a cryptographic **Salt** mechanism:
1. When a user registers or updates their password, the system leverages a Cryptographically Secure Pseudo-Random Number Generator (CSPRNG) to produce a globally unique, randomized string called a `Salt`.
2. The system concatenates the `plaintext password + Salt` before passing it to the hashing function, storing the final string as `[Salt + Hash Result]` inside the database database.
3. **Defense Principle Against Rainbow Tables:** Because every `Salt` is unique and randomized per account, even if two distinct users pick the exact same password (e.g., `password123`), the injection of different salts forces the final hash outputs to be completely distinct. This completely neutralizes precomputed universal rainbow tables. Attackers are forced to compile a dedicated, custom rainbow table for *each individual account*, an operation so computationally expensive that it is practically impossible—ensuring that user passwords remain secure even in the event of a full database breach.
