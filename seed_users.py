import os

import requests
from google.cloud import datastore


DOMAIN = os.environ["AUTH0_DOMAIN"]
MGMT_TOKEN = os.environ["AUTH0_MGMT_TOKEN"]
PASSWORD = os.environ["TARPAULIN_PASSWORD"]
CONNECTION = os.environ.get("AUTH0_CONNECTION", "Username-Password-Authentication")
USERS = [
    ("admin1@osu.com", "admin"),
    ("instructor1@osu.com", "instructor"),
    ("instructor2@osu.com", "instructor"),
    ("student1@osu.com", "student"),
    ("student2@osu.com", "student"),
    ("student3@osu.com", "student"),
    ("student4@osu.com", "student"),
    ("student5@osu.com", "student"),
    ("student6@osu.com", "student"),
]


def auth0(method, path, **kwargs):
    headers = kwargs.pop("headers", {})
    headers["Authorization"] = f"Bearer {MGMT_TOKEN}"
    headers["Content-Type"] = "application/json"
    return requests.request(
        method,
        f"https://{DOMAIN}/api/v2{path}",
        headers=headers,
        timeout=20,
        **kwargs,
    )


def get_sub(email):
    response = auth0("GET", f"/users-by-email?email={email}")
    response.raise_for_status()
    matches = response.json()
    if matches:
        user_id = matches[0]["user_id"]
        auth0(
            "PATCH",
            f"/users/{user_id}",
            json={"password": PASSWORD, "connection": CONNECTION},
        ).raise_for_status()
        return user_id
    response = auth0(
        "POST",
        "/users",
        json={
            "email": email,
            "password": PASSWORD,
            "connection": CONNECTION,
            "email_verified": True,
            "verify_email": False,
        },
    )
    response.raise_for_status()
    return response.json()["user_id"]


def main():
    client = datastore.Client()
    existing = list(client.query(kind="users").fetch())
    for entity in existing:
        client.delete(entity.key)
    for email, role in USERS:
        entity = datastore.Entity(key=client.key("users"))
        entity.update({"sub": get_sub(email), "role": role})
        client.put(entity)
        print(email, role, entity["sub"], entity.key.id)


if __name__ == "__main__":
    main()
