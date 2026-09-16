"""F015 G-01 ~ G-08：生产部署产物的静态 guard。

把「仅 nginx 对外 / 无默认凭据 / 探针不触 HTTP / 无越界能力 / 无破坏性命令 /
生产文档面关闭 / 连接池上限」变成会失败的测试，而非口头约定（架构 Test Work）。
"""

from __future__ import annotations

import re
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
COMPOSE = REPO_ROOT / "docker-compose.prod.yml"
NGINX_CONF = REPO_ROOT / "deploy" / "nginx" / "default.conf"
ENV_TEMPLATE = REPO_ROOT / "deploy" / "env.prod.example"
BACKEND_DOCKERFILE = REPO_ROOT / "backend" / "Dockerfile"
FRONTEND_DOCKERFILE = REPO_ROOT / "frontend" / "Dockerfile"
DEPLOY_DOC = REPO_ROOT / "docs" / "deployment" / "csm-v1-internal-deployment.md"

#: 生产产物（凭据 / 越界 / 破坏性命令 guard 的扫描范围）。
PRODUCTION_ARTIFACTS = [
    COMPOSE,
    NGINX_CONF,
    ENV_TEMPLATE,
    BACKEND_DOCKERFILE,
    FRONTEND_DOCKERFILE,
]

POSTGRES_MAX_CONNECTIONS = 100


def _compose() -> dict:
    return yaml.safe_load(COMPOSE.read_text(encoding="utf-8"))


def _healthcheck_test(service: dict) -> str:
    test = service.get("healthcheck", {}).get("test")
    if isinstance(test, list):
        return " ".join(str(part) for part in test)
    return str(test or "")


# --------------------------------------------------------------------------- #
# G-01：编排结构（仅 nginx 发布端口 / prod 标签 / 命名卷 / 依赖 / 探测 / restart）
# --------------------------------------------------------------------------- #
def test_g01_compose_services_and_exposure():
    compose = _compose()
    services = compose["services"]
    assert set(services) == {"postgres", "app", "nginx"}

    assert services["postgres"]["image"] == "postgres:16"

    # 仅 nginx 发布宿主端口。
    assert "ports" not in services["app"]
    assert "ports" not in services["postgres"]
    assert services["nginx"]["ports"] == ["${CSM_HTTP_PORT:-80}:80"]

    assert services["app"]["expose"] == ["8000"]
    assert services["postgres"]["expose"] == ["5432"]


def test_g01_app_environment_forces_prod_and_pool():
    app_env = _compose()["services"]["app"]["environment"]
    assert app_env["CSM_ENVIRONMENT"] == "prod"
    assert app_env["CSM_DB_POOL_SIZE"] == "5"
    assert app_env["CSM_DB_MAX_OVERFLOW"] == "10"


def test_g01_named_volume_mounted_at_pgdata():
    compose = _compose()
    assert "csm-prod-pgdata" in compose["volumes"]
    volumes = compose["services"]["postgres"]["volumes"]
    assert any(
        volume.startswith("csm-prod-pgdata:") and volume.endswith("/var/lib/postgresql/data")
        for volume in volumes
    ), volumes


def test_g01_restart_and_dependencies():
    services = _compose()["services"]
    for name in ("postgres", "app", "nginx"):
        assert services[name]["restart"] == "unless-stopped", name
    assert services["app"]["depends_on"]["postgres"]["condition"] == "service_healthy"
    assert services["nginx"]["depends_on"]["app"]["condition"] == "service_healthy"


def test_g01_healthchecks_exist_and_are_transport_level():
    services = _compose()["services"]
    assert "pg_isready" in _healthcheck_test(services["postgres"])

    app_probe = _healthcheck_test(services["app"])
    assert "127.0.0.1" in app_probe and "socket" in app_probe
    nginx_probe = _healthcheck_test(services["nginx"])
    assert "127.0.0.1" in nginx_probe and "nc " in nginx_probe


def test_g01_postgres_locale_fixed():
    env = _compose()["services"]["postgres"]["environment"]
    assert env["POSTGRES_INITDB_ARGS"] == "--encoding=UTF8 --locale=C.UTF-8"
    assert env["LANG"] == "C.UTF-8"
    assert env["LC_ALL"] == "C.UTF-8"


# --------------------------------------------------------------------------- #
# G-02：无字面量凭据 / 凭据仅以必填变量语法外部注入
# --------------------------------------------------------------------------- #
def test_g02_no_literal_credentials_in_production_artifacts():
    for path in PRODUCTION_ARTIFACTS:
        text = path.read_text(encoding="utf-8")
        assert "csm:csm" not in text, path
        assert re.search(r"postgresql(?:\+psycopg)?://[^\s\"']*:[^\s\"']*@", text) is None, path
        assert not re.search(r"POSTGRES_PASSWORD[ \t]*[:=][ \t]*[\"']?[A-Za-z0-9]", text), path


def test_g02_credentials_use_required_variable_syntax():
    text = COMPOSE.read_text(encoding="utf-8")
    for name in ("CSM_POSTGRES_USER", "CSM_POSTGRES_PASSWORD", "CSM_POSTGRES_DB"):
        assert f"${{{name}:?" in text, f"{name} 必须使用必填变量语法 ${{VAR:?…}}"


def test_g02_no_default_value_for_credential_variables():
    text = COMPOSE.read_text(encoding="utf-8")
    credential_tokens = ("PASSWORD", "PASS", "SECRET", "TOKEN", "CREDENTIAL", "DSN", "USER")
    offenders = []
    for match in re.finditer(r"\$\{([A-Z0-9_]+):-([^}]*)\}", text):
        name, default = match.group(1), match.group(2)
        if any(token in name for token in credential_tokens):
            offenders.append((name, default))
    # CSM_HTTP_PORT 的默认值不是凭据，允许存在。
    assert offenders == [], f"凭据变量不得带默认值：{offenders}"


def test_g02_env_template_has_empty_values_only():
    for line in ENV_TEMPLATE.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        assert stripped.endswith("="), f"模板值必须为空：{stripped!r}"
        assert not re.search(r"=\S", stripped), f"模板值必须为空：{stripped!r}"


def test_g02_dockerfiles_carry_no_credentials():
    for path in (BACKEND_DOCKERFILE, FRONTEND_DOCKERFILE):
        text = path.read_text(encoding="utf-8")
        assert "CSM_DATABASE_URL" not in text
        assert not re.search(r"PASSWORD\s*=", text), path


# --------------------------------------------------------------------------- #
# G-03：无越界能力（HTTPS / 域名 / 公网入口 / 编排平台 / 额外中间件）
# --------------------------------------------------------------------------- #
CONFIG_FORBIDDEN = [
    "443",
    "ssl_",
    "ssl ",
    "certificate",
    "server_name",
    "letsencrypt",
    "certbot",
    "kubernetes",
    "kubectl",
    "helm",
    "redis",
    "elasticsearch",
    "rabbitmq",
    "kafka",
    "prometheus",
    "grafana",
    "alertmanager",
]

DOC_FORBIDDEN = [
    "ssl_certificate",
    "listen 443",
    "certbot",
    "letsencrypt",
    "kubernetes.io",
    "kubectl",
    "helm install",
    "redis://",
    "image: redis",
]


def test_g03_no_out_of_scope_capability_in_config_artifacts():
    for path in PRODUCTION_ARTIFACTS:
        lowered = path.read_text(encoding="utf-8").lower()
        for token in CONFIG_FORBIDDEN:
            assert token not in lowered, f"{path} 含越界能力标记：{token!r}"


def test_g03_deployment_doc_has_no_out_of_scope_guidance():
    lowered = DEPLOY_DOC.read_text(encoding="utf-8").lower()
    for token in DOC_FORBIDDEN:
        assert token not in lowered, f"部署文档含越界指引：{token!r}"


# --------------------------------------------------------------------------- #
# G-04：生产产物与部署文档无破坏性命令
# --------------------------------------------------------------------------- #
FORBIDDEN_COMMANDS = ["alembic downgrade", "down -v", "docker volume rm"]


def test_g04_no_destructive_commands():
    for path in [*PRODUCTION_ARTIFACTS, DEPLOY_DOC]:
        text = path.read_text(encoding="utf-8").lower()
        for token in FORBIDDEN_COMMANDS:
            assert token not in text, f"{path} 含破坏性命令：{token!r}"


# --------------------------------------------------------------------------- #
# G-05：部署文档覆盖 AC-09 的 10 项
# --------------------------------------------------------------------------- #
def test_g05_deployment_document_covers_required_items():
    text = DEPLOY_DOC.read_text(encoding="utf-8")
    required = [
        "前置条件",
        "部署命令序列",
        "alembic upgrade head",
        "create-initial-admin",
        "端到端验证",
        "升级步骤",
        "datcollate",
        "datctype",
        "UTF8",
        "PostgreSQL 16",
        "连接池上限",
        "pool_size + max_overflow",
        "仅限受控内网",
        "Secure",
        "HttpOnly",
        "探测",
        "pg_isready",
        "账号停用",
        "README.md` §5.1",
    ]
    missing = [item for item in required if item not in text]
    assert missing == [], f"部署文档缺少条目：{missing}"


# --------------------------------------------------------------------------- #
# G-06：nginx 配置
# --------------------------------------------------------------------------- #
def test_g06_nginx_listens_80_and_serves_spa():
    text = NGINX_CONF.read_text(encoding="utf-8")
    assert re.search(r"listen\s+80\b[^;]*;", text)
    assert re.search(r"root\s+/usr/share/nginx/html\s*;", text)
    assert "try_files $uri $uri/ /index.html;" in text


def test_g06_nginx_proxies_api_to_app():
    text = NGINX_CONF.read_text(encoding="utf-8")
    assert "location /api/" in text
    assert "proxy_pass http://app:8000" in text
    # 保留路径 / 方法 / Cookie / Host。
    assert "proxy_set_header Host $host;" in text
    assert "proxy_set_header Cookie $http_cookie;" in text


def test_g06_nginx_blocks_framework_docs_before_fallback():
    text = NGINX_CONF.read_text(encoding="utf-8")
    fallback_index = text.index("location / {")
    for path in ("/docs", "/redoc", "/openapi.json"):
        assert f"location = {path}" in text, path
        assert text.index(f"location = {path}") < fallback_index, path
    assert text.count("return 404;") >= 3


def test_g06_nginx_has_no_tls_or_domain_directives():
    lowered = NGINX_CONF.read_text(encoding="utf-8").lower()
    assert "ssl" not in lowered
    assert "443" not in lowered
    assert "server_name" not in lowered
    assert "certificate" not in lowered


# --------------------------------------------------------------------------- #
# G-07：探针不变量（不发起 HTTP / 不触及 /api / 不新增豁免）
# --------------------------------------------------------------------------- #
def test_g07_probes_do_not_use_http_or_api():
    compose_text = COMPOSE.read_text(encoding="utf-8").lower()
    dockerfile_text = BACKEND_DOCKERFILE.read_text(encoding="utf-8").lower()
    for label, text in (("compose", compose_text), ("backend Dockerfile", dockerfile_text)):
        assert "curl" not in text, label
        assert "wget" not in text, label
        assert "http://" not in text, label
        assert "/api" not in text, label


def test_g07_no_healthcheck_instruction_in_backend_image():
    assert "healthcheck" not in BACKEND_DOCKERFILE.read_text(encoding="utf-8").lower()


def test_g07_exempt_set_unchanged():
    from app.auth.middleware import EXEMPT

    assert EXEMPT == {("POST", "/api/auth/login")}


def test_g07_no_http_probe_route_outside_api():
    from app.config import Settings
    from app.main import create_app
    from tests.conftest import OFFLINE_DSN

    app = create_app(Settings(environment="dev", database_url=OFFLINE_DSN))
    for path in app.openapi()["paths"]:
        assert path.startswith("/api"), f"产品路由必须在 /api 下：{path}"


# --------------------------------------------------------------------------- #
# G-08：连接池上限显式且低于 max_connections
# --------------------------------------------------------------------------- #
def test_g08_pool_limit_below_max_connections():
    env = _compose()["services"]["app"]["environment"]
    pool_size = int(env["CSM_DB_POOL_SIZE"])
    max_overflow = int(env["CSM_DB_MAX_OVERFLOW"])
    assert pool_size + max_overflow < POSTGRES_MAX_CONNECTIONS


def test_g08_pool_limit_documented():
    text = DEPLOY_DOC.read_text(encoding="utf-8")
    assert "5 + 10 = 15" in text
    assert "max_connections" in text
