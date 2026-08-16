# Tarpaulin REST API

Tarpaulin is a role-based course management API built with Python and Flask. It implements a 13-endpoint REST interface for users, courses, enrollments, and profile avatars, backed by Google Cloud Datastore and Cloud Storage with Auth0-issued JSON Web Tokens (JWTs).

This repository is the public portfolio version of my final project for Oregon State University's cloud application development coursework. The original course deployment is no longer active, so this repository documents the implementation rather than advertising a live demo.

## What it demonstrates

- REST resource design with consistent JSON responses and HTTP status codes
- Authentication through Auth0 and server-side JWT verification against JSON Web Key Sets (JWKS)
- Role-based authorization for administrators, instructors, and students
- Google Cloud Datastore queries and CRUD operations
- Google Cloud Storage uploads, downloads, and deletion for user avatars
- Course pagination, ordering, partial updates, and enrollment management
- Environment-based configuration for credentials and deployment-specific values

## Architecture

| Component | Responsibility |
| --- | --- |
| Flask application | Routes requests, validates input, and returns API responses |
| Auth0 | Authenticates predefined users and issues signed JWTs |
| Google Cloud Datastore | Stores user roles, course records, and enrollment IDs |
| Google Cloud Storage | Stores avatar image objects |
| Google App Engine | Hosts the Flask service |

The API never stores passwords in Datastore. User identity comes from the JWT `sub` claim, while application roles remain in the `users` kind.

## Endpoint summary

| Method | Endpoint | Access | Purpose |
| --- | --- | --- | --- |
| `POST` | `/users/login` | Public, predefined users | Exchange Auth0 credentials for a JWT |
| `GET` | `/users` | Admin | List all users |
| `GET` | `/users/:id` | Admin or matching user | Get a user, avatar URL, and role-specific courses |
| `POST` | `/users/:id/avatar` | Matching user | Create or replace an avatar |
| `GET` | `/users/:id/avatar` | Matching user | Download an avatar |
| `DELETE` | `/users/:id/avatar` | Matching user | Delete an avatar |
| `POST` | `/courses` | Admin | Create a course |
| `GET` | `/courses` | Public | List courses ordered by subject with limit/offset pagination |
| `GET` | `/courses/:id` | Public | Get one course |
| `PATCH` | `/courses/:id` | Admin | Partially update a course |
| `DELETE` | `/courses/:id` | Admin | Delete a course and its embedded enrollment data |
| `PATCH` | `/courses/:id/students` | Admin or assigned instructor | Add or remove enrolled students |
| `GET` | `/courses/:id/students` | Admin or assigned instructor | List enrolled student IDs |

Protected endpoints expect `Authorization: Bearer <JWT>`.

## Data model

### `users`

| Property | Type | Required | Description |
| --- | --- | --- | --- |
| `id` | Integer | Yes | Datastore-generated entity ID |
| `sub` | String | Yes | Auth0 subject used to match a JWT to a user |
| `role` | String | Yes | `admin`, `instructor`, or `student` |
| `avatar` | String | No | Randomized Cloud Storage object name |

### `courses`

| Property | Type | Required | Description |
| --- | --- | --- | --- |
| `id` | Integer | Yes | Datastore-generated entity ID |
| `subject` | String | Yes | Course subject code |
| `number` | Integer | Yes | Course number |
| `title` | String | Yes | Course title |
| `term` | String | Yes | Academic term |
| `instructor_id` | Integer | Yes | Datastore ID of the assigned instructor |
| `students` | Array of integers | Yes | Datastore IDs of enrolled students |

Enrollment is embedded in each course as student IDs. Deleting a course therefore removes its enrollment information with the same Datastore entity.

## Run locally

Prerequisites:

- Python 3.11 or newer
- A Google Cloud project with Datastore and Cloud Storage configured
- Google Application Default Credentials
- An Auth0 application configured for the password grant used by this assignment

Create a virtual environment and install the dependencies:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

Copy `.env.example` to a private `.env` file, replace every placeholder, and export those variables into your shell. This application deliberately does not load `.env` files itself.

```bash
set -a
source .env
set +a
flask --app main run --debug
```

The API starts at `http://127.0.0.1:5000`. A simple health response is available from `GET /`.

## Seed the predefined users

`seed_users.py` creates the assignment's nine Auth0 users and corresponding Datastore entities. It requires `AUTH0_DOMAIN`, `AUTH0_MGMT_TOKEN`, `AUTH0_CONNECTION`, and `TARPAULIN_PASSWORD`.

> **Warning:** the script deletes every existing entity in the Datastore `users` kind before recreating the nine assignment users. Run it only against a dedicated development or course project.

```bash
python seed_users.py
```

Use a short-lived Auth0 Management API token and never commit `.env`, service-account keys, passwords, or the original submission PDF.

## Deploy to App Engine

The checked-in `app.yaml.example` is a safe template. Copy it to the ignored `app.yaml`, replace its four placeholder values, then deploy from an authenticated Google Cloud CLI session:

```bash
cp app.yaml.example app.yaml
# Edit the private app.yaml values.
gcloud app deploy app.yaml
```

For a maintained production service, configure secrets through a managed secret store instead of App Engine environment values committed to source control.

## Verification and project scope

The source files compile with Python 3.12, and the included unit tests verify application import, the health response, bearer-token parsing, and registration of all 13 assignment endpoints:

```bash
python -m unittest discover -s tests -v
```

The course also used Postman/Newman API checks against a deployed GCP environment; those instructor-provided tests and the credential-bearing submission PDF are not included here.

This is an educational implementation, not a production identity or learning-management system. Production hardening would include comprehensive endpoint and cloud-integration tests, stricter request and upload validation, temporary-file cleanup or streamed downloads, rate limiting, structured logging, cursor-based pagination, secret-manager integration, and a modern interactive Auth0 authorization flow instead of the assignment-required password grant.
