"""Authentication, role gates, and opaque database-backed login sessions."""

from hashlib import sha256
import secrets

from argon2 import PasswordHasher
from argon2.exceptions import VerificationError
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from campus_market.errors import DomainError, require
from campus_market.models import LoginSession, OperationLog, User
from campus_market.validation import account_fields

PASSWORDS = PasswordHasher(time_cost=2, memory_cost=19456, parallelism=1)
DUMMY_HASH = PASSWORDS.hash(secrets.token_urlsafe(24))


def digest(value: str) -> str:
    """One-way representation for bearer tokens and CSRF bindings."""
    return sha256(value.encode()).hexdigest()


def public_user(user: User) -> dict:
    """Explicit output whitelist excludes password hashes and session material."""
    return {"id": user.id, "username": user.username, "nickname": user.nickname, "role": user.role}


def require_user(actor: User | None) -> User:
    """A missing session never falls back to an actor supplied in a request."""
    require(actor is not None, "LOGIN_REQUIRED", "请先登录", 401)
    return actor


def require_role(actor: User | None, role: str) -> User:
    """Administrative accounts cannot participate in ordinary trading."""
    actor = require_user(actor)
    require(actor.role == role, "FORBIDDEN", "当前账号无权执行此操作", 403)
    return actor


class AuthService:
    """Own authentication transactions separately from marketplace commands."""

    def __init__(self, database):
        self.database = database

    def register(self, username: str, password: str, nickname: str = "", *, role: str = "USER") -> dict:
        """The role keyword is only available to the trusted initialization CLI."""
        username, nickname = account_fields(username, password, nickname)
        require(role in ("USER", "ADMIN"), "ROLE", "非法角色", 422)
        hashed = PASSWORDS.hash(password)
        try:
            with self.database.sessions.begin() as session:
                user = User(username=username, nickname=nickname, password_hash=hashed, role=role)
                session.add(user)
                session.flush()
                session.add(OperationLog(actor_id=user.id, role_at_time=role, target_type="user",
                                         target_id=user.id, action="register", result="SUCCESS"))
                result = public_user(user)
            return result
        except IntegrityError as exc:
            raise DomainError("USERNAME_EXISTS", "用户名已存在", 409, "username") from exc

    def login(self, username: str, password: str) -> tuple[dict, str, str]:
        """Uniform errors and a dummy hash avoid disclosing account existence."""
        with self.database.sessions.begin() as session:
            user = session.scalar(select(User).where(User.username == username.lower()))
            valid = False
            try:
                valid = PASSWORDS.verify(user.password_hash if user else DUMMY_HASH, password)
            except VerificationError:
                valid = False
            if user is None or not valid:
                rejected_id = user.id if user else None
            else:
                token, csrf = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
                session.add(LoginSession(token_hash=digest(token), user_id=user.id, csrf_hash=digest(csrf)))
                session.add(OperationLog(actor_id=user.id, role_at_time=user.role, target_type="user",
                                         target_id=user.id, action="login", result="SUCCESS"))
                return public_user(user), token, csrf
        self.record_failure(rejected_id, "login", "BAD_CREDENTIALS")
        raise DomainError("BAD_CREDENTIALS", "用户名或密码错误", 401)

    def resolve(self, token: str) -> tuple[User | None, str]:
        """Return a detached identity and CSRF digest, never the password hash."""
        if not token:
            return None, ""
        with self.database.sessions() as session:
            login = session.get(LoginSession, digest(token))
            if login is None:
                return None, ""
            user = session.get(User, login.user_id)
            session.expunge(user)
            return user, login.csrf_hash

    def logout(self, token: str):
        """Revoke the current login rather than merely discarding a client cookie."""
        with self.database.sessions.begin() as session:
            login = session.get(LoginSession, digest(token))
            if login:
                user = session.get(User, login.user_id)
                session.add(OperationLog(actor_id=user.id, role_at_time=user.role, target_type="user",
                                         target_id=user.id, action="logout", result="SUCCESS"))
                session.execute(delete(LoginSession).where(LoginSession.token_hash == digest(token)))

    def record_failure(self, actor_id: str | None, action: str, code: str, target_id: str = ""):
        """Failure logging is best effort and can never turn rejection into success."""
        try:
            with self.database.sessions.begin() as session:
                user = session.get(User, actor_id) if actor_id else None
                session.add(OperationLog(actor_id=actor_id, role_at_time=user.role if user else "GUEST",
                                         target_type="request", target_id=target_id[:36], action=action[:40],
                                         result="FAILURE", failure_code=code[:40]))
        except SQLAlchemyError:
            # The caller still returns the original rejection when audit storage is unavailable.
            pass
