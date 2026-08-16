import json
import os
import uuid
from urllib.request import urlopen

import requests
from flask import Flask, jsonify, request, send_file
from google.cloud import datastore, storage
from jose import jwt


app = Flask(__name__)

USERS = "users"
COURSES = "courses"
ALGORITHMS = ["RS256"]
ERRORS = {
    400: {"Error": "The request body is invalid"},
    401: {"Error": "Unauthorized"},
    403: {"Error": "You don't have permission on this resource"},
    404: {"Error": "Not found"},
}

CLIENT_ID = os.environ.get("AUTH0_CLIENT_ID", "")
CLIENT_SECRET = os.environ.get("AUTH0_CLIENT_SECRET", "")
DOMAIN = os.environ.get("AUTH0_DOMAIN", "")
GCS_BUCKET = os.environ.get("GCS_BUCKET", "")

ds = datastore.Client()
storage_client = storage.Client()


class AuthError(Exception):
    pass


@app.errorhandler(AuthError)
def auth_error(_):
    return jsonify(ERRORS[401]), 401


def err(status):
    return jsonify(ERRORS[status]), status


def base_url():
    scheme = request.headers.get("X-Forwarded-Proto", request.scheme)
    return f"{scheme}://{request.host}"


def course_url(course_id):
    return f"{base_url()}/courses/{course_id}"


def avatar_url(user_id):
    return f"{base_url()}/users/{user_id}/avatar"


def user_key(user_id):
    return ds.key(USERS, user_id)


def course_key(course_id):
    return ds.key(COURSES, course_id)


def get_token(req):
    parts = req.headers.get("Authorization", "").split()
    if len(parts) != 2 or parts[0].lower() != "bearer":
        raise AuthError()
    return parts[1]


def verify_jwt(req):
    token = get_token(req)
    try:
        jwks = json.loads(urlopen(f"https://{DOMAIN}/.well-known/jwks.json").read())
        header = jwt.get_unverified_header(token)
        rsa_key = next(
            (
                {"kty": k["kty"], "kid": k["kid"], "use": k["use"], "n": k["n"], "e": k["e"]}
                for k in jwks["keys"]
                if k["kid"] == header.get("kid")
            ),
            None,
        )
        if not rsa_key or header.get("alg") != "RS256":
            raise AuthError()
        return jwt.decode(
            token,
            rsa_key,
            algorithms=ALGORITHMS,
            audience=CLIENT_ID,
            issuer=f"https://{DOMAIN}/",
        )
    except Exception as exc:
        if isinstance(exc, AuthError):
            raise
        raise AuthError()


def current_user():
    payload = verify_jwt(request)
    query = ds.query(kind=USERS)
    query.add_filter(filter=datastore.query.PropertyFilter("sub", "=", payload["sub"]))
    users = list(query.fetch(limit=1))
    if not users:
        raise AuthError()
    return users[0]


def is_admin(user):
    return user.get("role") == "admin"


def is_instructor(user):
    return user.get("role") == "instructor"


def user_summary(entity):
    return {"id": entity.key.id, "role": entity["role"], "sub": entity["sub"]}


def course_dict(entity):
    return {
        "id": entity.key.id,
        "instructor_id": entity["instructor_id"],
        "number": entity["number"],
        "self": course_url(entity.key.id),
        "subject": entity["subject"],
        "term": entity["term"],
        "title": entity["title"],
    }


def user_detail(entity):
    data = user_summary(entity)
    if entity.get("avatar"):
        data["avatar_url"] = avatar_url(entity.key.id)
    if entity["role"] == "instructor":
        query = ds.query(kind=COURSES)
        query.add_filter(filter=datastore.query.PropertyFilter("instructor_id", "=", entity.key.id))
        data["courses"] = [course_url(c.key.id) for c in query.fetch()]
    elif entity["role"] == "student":
        query = ds.query(kind=COURSES)
        query.add_filter(filter=datastore.query.PropertyFilter("students", "=", entity.key.id))
        data["courses"] = [course_url(c.key.id) for c in query.fetch()]
    return data


def get_bucket():
    return storage_client.bucket(GCS_BUCKET)


def valid_instructor(user_id):
    user = ds.get(user_key(user_id))
    return user is not None and user.get("role") == "instructor"


def valid_students(ids):
    for student_id in ids:
        user = ds.get(user_key(student_id))
        if user is None or user.get("role") != "student":
            return False
    return True


@app.route("/", methods=["GET"])
def index():
    return "Tarpaulin API is running", 200


@app.route("/users/login", methods=["POST"])
def login():
    body = request.get_json(silent=True)
    if not body or "username" not in body or "password" not in body:
        return err(400)
    auth_body = {
        "grant_type": "password",
        "username": body["username"],
        "password": body["password"],
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "scope": "openid profile email",
    }
    response = requests.post(
        f"https://{DOMAIN}/oauth/token",
        json=auth_body,
        headers={"content-type": "application/json"},
        timeout=10,
    )
    if response.status_code != 200:
        return err(401)
    token = response.json().get("id_token") or response.json().get("access_token")
    return jsonify({"token": token}), 200


@app.route("/users", methods=["GET"])
def get_users():
    user = current_user()
    if not is_admin(user):
        return err(403)
    return jsonify([user_summary(u) for u in ds.query(kind=USERS).fetch()]), 200


@app.route("/users/<int:user_id>", methods=["GET"])
def get_user(user_id):
    requester = current_user()
    target = ds.get(user_key(user_id))
    if target is None:
        return err(403)
    if not is_admin(requester) and requester.key.id != user_id:
        return err(403)
    return jsonify(user_detail(target)), 200


@app.route("/users/<int:user_id>/avatar", methods=["POST"])
def upload_avatar(user_id):
    if "file" not in request.files:
        return err(400)
    requester = current_user()
    if requester.key.id != user_id:
        return err(403)
    user = ds.get(user_key(user_id))
    if user is None:
        return err(403)
    if user.get("avatar"):
        get_bucket().blob(user["avatar"]).delete()
    filename = f"{uuid.uuid4()}.png"
    blob = get_bucket().blob(filename)
    blob.upload_from_file(request.files["file"], content_type="image/png")
    user["avatar"] = filename
    ds.put(user)
    return jsonify({"avatar_url": avatar_url(user_id)}), 200


@app.route("/users/<int:user_id>/avatar", methods=["GET"])
def get_avatar(user_id):
    requester = current_user()
    if requester.key.id != user_id:
        return err(403)
    user = ds.get(user_key(user_id))
    if user is None or not user.get("avatar"):
        return err(404)
    path = f"/tmp/{user['avatar']}"
    get_bucket().blob(user["avatar"]).download_to_filename(path)
    return send_file(path, mimetype="image/png"), 200


@app.route("/users/<int:user_id>/avatar", methods=["DELETE"])
def delete_avatar(user_id):
    requester = current_user()
    if requester.key.id != user_id:
        return err(403)
    user = ds.get(user_key(user_id))
    if user is None or not user.get("avatar"):
        return err(404)
    get_bucket().blob(user["avatar"]).delete()
    del user["avatar"]
    ds.put(user)
    return "", 204


@app.route("/courses", methods=["POST"])
def create_course():
    body = request.get_json(silent=True)
    required = ["subject", "number", "title", "term", "instructor_id"]
    if not body or any(k not in body for k in required):
        return err(400)
    user = current_user()
    if not is_admin(user):
        return err(403)
    if not valid_instructor(body["instructor_id"]):
        return jsonify({"Error": "The value of instructor_id is invalid"}), 409
    entity = datastore.Entity(key=ds.key(COURSES))
    entity.update({k: body[k] for k in required})
    entity["students"] = []
    ds.put(entity)
    return jsonify(course_dict(entity)), 201


@app.route("/courses", methods=["GET"])
def get_courses():
    limit = int(request.args.get("limit", 3))
    offset = int(request.args.get("offset", 0))
    query = ds.query(kind=COURSES)
    query.order = ["subject"]
    courses = [course_dict(c) for c in query.fetch(limit=limit, offset=offset)]
    data = {"courses": courses}
    if len(courses) == limit:
        data["next"] = f"{base_url()}/courses?limit={limit}&offset={offset + limit}"
    return jsonify(data), 200


@app.route("/courses/<int:course_id>", methods=["GET"])
def get_course(course_id):
    course = ds.get(course_key(course_id))
    if course is None:
        return err(404)
    return jsonify(course_dict(course)), 200


@app.route("/courses/<int:course_id>", methods=["PATCH"])
def update_course(course_id):
    body = request.get_json(silent=True)
    if body is None:
        return err(400)
    user = current_user()
    course = ds.get(course_key(course_id))
    if course is None:
        return err(403)
    if not is_admin(user):
        return err(403)
    if "instructor_id" in body and not valid_instructor(body["instructor_id"]):
        return jsonify({"Error": "The value of instructor_id is invalid"}), 409
    for field in ["subject", "number", "title", "term", "instructor_id"]:
        if field in body:
            course[field] = body[field]
    ds.put(course)
    return jsonify(course_dict(course)), 200


@app.route("/courses/<int:course_id>", methods=["DELETE"])
def delete_course(course_id):
    user = current_user()
    course = ds.get(course_key(course_id))
    if course is None:
        return err(403)
    if not is_admin(user):
        return err(403)
    ds.delete(course.key)
    return "", 204


@app.route("/courses/<int:course_id>/students", methods=["PATCH"])
def update_enrollment(course_id):
    user = current_user()
    course = ds.get(course_key(course_id))
    if course is None:
        return err(403)
    if not is_admin(user) and not (is_instructor(user) and user.key.id == course["instructor_id"]):
        return err(403)
    body = request.get_json(silent=True) or {}
    add = body.get("add", [])
    remove = body.get("remove", [])
    if set(add).intersection(remove) or not valid_students(add + remove):
        return jsonify({"Error": "Enrollment data is invalid"}), 409
    enrolled = set(course.get("students", []))
    enrolled.update(add)
    enrolled.difference_update(remove)
    course["students"] = list(enrolled)
    ds.put(course)
    return "", 200


@app.route("/courses/<int:course_id>/students", methods=["GET"])
def get_enrollment(course_id):
    user = current_user()
    course = ds.get(course_key(course_id))
    if course is None:
        return err(403)
    if not is_admin(user) and not (is_instructor(user) and user.key.id == course["instructor_id"]):
        return err(403)
    return jsonify(course.get("students", [])), 200


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)), debug=True)
