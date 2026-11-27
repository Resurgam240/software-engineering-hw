"""FastAPI boundary: strict inputs, session-derived identity, CSRF, and safe errors."""

from contextlib import asynccontextmanager
import hmac
from pathlib import Path
import secrets
from uuid import UUID

from fastapi import Depends, FastAPI, File, Request, UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from campus_market import schemas
from campus_market.assets import AssetService
from campus_market.auth import AuthService, digest, public_user, require_user
from campus_market.commands import CommandService
from campus_market.config import Settings
from campus_market.constants import CATEGORIES, CONDITIONS, STATUS_LABELS
from campus_market.db import Database
from campus_market.errors import DomainError, require
from campus_market.queries import QueryService

PACKAGE = Path(__file__).parent


# Route closures intentionally share per-application services, not global pools.
# pylint: disable-next=too-many-locals,too-many-statements
def create_app(settings: Settings | None = None) -> FastAPI:
    """The application factory enables isolated test pools and installed-wheel startup."""
    settings = settings or Settings.from_env()
    database = Database(settings)
    auth = AuthService(database)
    commands = CommandService(database, settings)
    queries = QueryService(database)
    assets = AssetService(database, settings.asset_dir)
    templates = Jinja2Templates(directory=str(PACKAGE / "templates"))

    @asynccontextmanager
    async def lifespan(_app):
        yield
        database.close()

    app = FastAPI(title="校园二手交易系统", version="1.0.0", lifespan=lifespan)
    app.state.database = database
    app.state.settings = settings
    app.mount("/static", StaticFiles(directory=PACKAGE / "static"), name="static")

    def identity(request: Request):
        actor, csrf_hash = auth.resolve(request.cookies.get("campus_session", ""))
        request.state.actor = actor
        request.state.csrf_hash = csrf_hash
        return actor

    def write_identity(request: Request, actor=Depends(identity)):
        token = request.headers.get("x-csrf-token", "")
        cookie = request.cookies.get("campus_csrf", "")
        origin = request.headers.get("origin")
        expected_origin = f"{request.url.scheme}://{request.url.netloc}"
        require(origin in (None, expected_origin), "CSRF", "请求来源校验失败，请刷新页面", 403)
        require(bool(token) and bool(cookie) and hmac.compare_digest(token, cookie),
                "CSRF", "请求校验失败，请刷新页面", 403)
        if actor:
            require(hmac.compare_digest(digest(token), request.state.csrf_hash),
                    "CSRF", "会话校验失败，请刷新页面", 403)
        return actor

    def key(request):
        return request.headers.get("idempotency-key", "")

    @app.middleware("http")
    async def response_headers(request: Request, call_next):
        response = await call_next(request)
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "same-origin"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' blob:; "
            "frame-ancestors 'none'; base-uri 'self'; form-action 'self'"
        )
        setting_csrf = any("campus_csrf=" in value for value in response.headers.getlist("set-cookie"))
        if not request.cookies.get("campus_csrf") and not setting_csrf:
            response.set_cookie("campus_csrf", secrets.token_urlsafe(32), secure=settings.secure_cookie,
                                httponly=False, samesite="strict")
        return response

    @app.exception_handler(DomainError)
    async def domain_error(request: Request, error: DomainError):
        actor = getattr(request.state, "actor", None)
        auth.record_failure(actor.id if actor else None, "http-rejection", error.code)
        return JSONResponse(error.payload(), status_code=error.status)

    @app.exception_handler(RequestValidationError)
    async def validation_error(_request: Request, error: RequestValidationError):
        # FastAPI's default includes rejected input, which may contain passwords or messages.
        fields = [".".join(str(item) for item in item["loc"][1:]) for item in error.errors()]
        return JSONResponse({"code": "INVALID_INPUT", "message": "字段缺失、类型错误或包含不允许的字段",
                             "fields": fields}, status_code=422)

    @app.exception_handler(SQLAlchemyError)
    async def storage_error(_request: Request, _error: SQLAlchemyError):
        return JSONResponse({"code": "STORAGE_UNAVAILABLE", "message": "存储暂不可用，请保留输入并用原标识重试"},
                            status_code=503)

    @app.get("/health")
    def health():
        with database.sessions() as session:
            session.execute(text("SELECT 1"))
        return {"status": "ok"}

    @app.get("/api/me")
    def me(actor=Depends(identity)):
        return {"user": public_user(actor) if actor else None}

    @app.post("/auth/register", status_code=201)
    def register(data: schemas.RegisterInput, _actor=Depends(write_identity)):
        require(_actor is None, "ALREADY_LOGGED_IN", "请先退出当前账号", 409)
        return auth.register(**data.model_dump())

    @app.post("/auth/login")
    def login(data: schemas.LoginInput, _actor=Depends(write_identity)):
        require(_actor is None, "ALREADY_LOGGED_IN", "请先退出当前账号", 409)
        user, token, csrf = auth.login(**data.model_dump())
        response = JSONResponse({"user": user})
        response.set_cookie("campus_session", token, httponly=True,
                            secure=settings.secure_cookie, samesite="strict")
        response.set_cookie("campus_csrf", csrf, httponly=False,
                            secure=settings.secure_cookie, samesite="strict")
        return response

    @app.post("/auth/logout")
    def logout(request: Request, actor=Depends(write_identity)):
        require_user(actor)
        auth.logout(request.cookies.get("campus_session", ""))
        response = JSONResponse({"message": "已退出"})
        response.delete_cookie("campus_session")
        response.set_cookie("campus_csrf", secrets.token_urlsafe(32), samesite="strict",
                            secure=settings.secure_cookie)
        return response

    @app.get("/api/products")
    def products(request: Request, actor=Depends(identity)):
        return queries.products(actor, dict(request.query_params))

    @app.get("/api/me/products")
    def my_products(request: Request, actor=Depends(identity)):
        return queries.products(actor, dict(request.query_params), "mine")

    @app.get("/api/admin/products")
    def admin_products(request: Request, actor=Depends(identity)):
        return queries.products(actor, dict(request.query_params), "admin")

    @app.get("/api/products/{product_id}")
    def product(product_id: UUID, actor=Depends(identity)):
        return queries.product(actor, str(product_id))

    @app.post("/api/products", status_code=201)
    def create_product(data: schemas.ContentInput, request: Request, actor=Depends(write_identity)):
        return commands.execute(actor, "product.create", key(request), data.model_dump())

    @app.patch("/api/products/{product_id}")
    def edit_product(product_id: UUID, data: schemas.EditInput, request: Request,
                     actor=Depends(write_identity)):
        return commands.execute(actor, "product.edit", key(request),
                                {**data.model_dump(), "product_id": str(product_id)})

    def add_product_action(action, schema, method="POST"):
        def endpoint(product_id: UUID, data, request: Request, actor=Depends(write_identity)):
            return commands.execute(actor, "product." + action, key(request),
                                    {**data.model_dump(), "product_id": str(product_id)})
        endpoint.__annotations__["data"] = schema
        app.add_api_route("/api/products/{product_id}" + ("/" + action if method == "POST" else ""),
                          endpoint, methods=[method], name="product_" + action)

    add_product_action("submit", schemas.SubmitInput)
    add_product_action("withdraw", schemas.WithdrawInput)
    add_product_action("take-down", schemas.StateInput)
    add_product_action("delete", schemas.StateInput, "DELETE")

    def add_governance_action(action, schema):
        def endpoint(product_id: UUID, data, request: Request, actor=Depends(write_identity)):
            return commands.execute(actor, action, key(request),
                                    {**data.model_dump(), "product_id": str(product_id)})
        endpoint.__annotations__["data"] = schema
        app.add_api_route("/api/admin/products/{product_id}/" + action, endpoint,
                          methods=["POST"], name=action)

    add_governance_action("review", schemas.ReviewInput)
    add_governance_action("violation", schemas.ViolationInput)

    @app.post("/api/reservations", status_code=201)
    def reserve(data: schemas.ReserveInput, request: Request, actor=Depends(write_identity)):
        return commands.execute(actor, "reservation.create", key(request), data.model_dump())

    @app.get("/api/reservations")
    def reservations(request: Request, actor=Depends(identity)):
        return queries.reservations(actor, dict(request.query_params))

    @app.get("/api/reservations/{reservation_id}")
    def reservation(reservation_id: UUID, actor=Depends(identity)):
        return queries.reservation(actor, str(reservation_id))

    def add_reservation_action(action, schema):
        def endpoint(reservation_id: UUID, data, request: Request, actor=Depends(write_identity)):
            return commands.execute(actor, "reservation." + action, key(request),
                                    {**data.model_dump(), "reservation_id": str(reservation_id)})
        endpoint.__annotations__["data"] = schema
        app.add_api_route("/api/reservations/{reservation_id}/" + action, endpoint,
                          methods=["POST"], name="reservation_" + action)

    for action in ("confirm", "complete", "reject", "cancel"):
        add_reservation_action(action, schemas.ReservationReasonInput if action in ("reject", "cancel")
                               else schemas.ReservationStateInput)

    @app.get("/api/statistics/completed")
    def statistics(request: Request, actor=Depends(identity)):
        return queries.statistics(actor, dict(request.query_params))

    @app.get("/api/history")
    def history(request: Request, actor=Depends(identity)):
        return queries.history(actor, dict(request.query_params))

    @app.post("/api/admin/reservations/{reservation_id}/private-message-access")
    def private_message(reservation_id: UUID, data: schemas.PrivateAccessInput,
                        actor=Depends(write_identity)):
        return queries.private_message(actor, str(reservation_id), **data.model_dump())

    @app.post("/api/images", status_code=201)
    async def upload_image(file: UploadFile = File(...), actor=Depends(write_identity)):
        content = await file.read(5 * 1024 * 1024 + 1)
        return assets.upload(actor, content, file.filename or "")

    @app.get("/images/{image_id}")
    def image(image_id: UUID, actor=Depends(identity)):
        path, mime = assets.read(actor, str(image_id))
        return FileResponse(path, media_type=mime)

    @app.get("/")
    @app.get("/login")
    @app.get("/market")
    @app.get("/my-products")
    @app.get("/my-reservations")
    @app.get("/seller-reservations")
    @app.get("/statistics")
    @app.get("/history")
    @app.get("/admin")
    @app.get("/product/{product_id}")
    @app.get("/reservation/{reservation_id}")
    def page(request: Request, actor=Depends(identity)):
        return templates.TemplateResponse(request=request, name="app.html", context={
            "actor": public_user(actor) if actor else None, "categories": CATEGORIES,
            "conditions": CONDITIONS, "labels": STATUS_LABELS,
        })

    return app
