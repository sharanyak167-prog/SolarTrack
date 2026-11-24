"""Create the first administrator interactively; run from the backend directory."""
import getpass
from sqlalchemy import select
from app import config, db
from app.auth import hash_password, jwt_secret
from app.models import User


def main():
    jwt_secret()
    db.init_db(config.database_url())
    username = input("Administrator username: ").strip()
    password = getpass.getpass("Administrator password (at least 12 characters): ")
    confirm = getpass.getpass("Confirm password: ")
    if not username or len(username) > 60 or len(password) < 12 or len(password.encode()) > 72 or password != confirm:
        raise SystemExit("Invalid username or password, or passwords do not match.")
    with db.SessionLocal() as s:
        if s.scalar(select(User.id)) is not None:
            raise SystemExit("Users already exist. Use the administrator user management screen.")
        s.add(User(username=username, hashed_password=hash_password(password), role="admin", is_active=True))
        s.commit()
    print("Administrator created.")

if __name__ == "__main__":
    main()
