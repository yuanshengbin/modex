#!/usr/bin/env bash
# =============================================================================
# MODEX AI Backend 一键部署脚本（Linux）
#
# 类比：这个脚本就像一位“搬家工人”，按固定顺序帮你完成——
#   装系统工具 → 搭 Python 独立小房间(venv) → 安装依赖 → 检查配置
#   → 注册 systemd 服务(开机自启的管家) → 启动服务 → 健康检查。
#
# 用法：
#   首次部署：   sudo bash deploy.sh
#   更新部署：   sudo bash deploy.sh update   # 重装依赖并重启服务
#   仅重启：     sudo bash deploy.sh restart
#
# 支持系统：Ubuntu / Debian（apt）、CentOS / RHEL / Rocky（dnf|yum）
# =============================================================================

# -e: 任何命令失败立即退出；-u: 使用未定义变量时报错；
# -o pipefail: 管道中任一环节失败都算失败。三件套保证脚本“出错就停”，不带病运行。
set -euo pipefail

# --------------------------- 可配置变量（按需修改） ---------------------------
APP_NAME="modex"          # systemd 服务名，也是日志目录名
PORT=8000                 # 服务监听端口（与 Nginx 反代目标端口对应）
WORKERS=4                 # gunicorn worker 进程数，建议 = CPU 核数的 1~2 倍

# APP_DIR = 脚本所在的目录，即项目根目录。这样脚本无论从哪里执行都能找到项目文件。
APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# 真正运行服务的系统用户：若用 sudo 执行，则取“发起 sudo 的那个普通用户”，否则取当前用户。
# 目的：服务不以 root 身份运行，降低安全风险。
SERVICE_USER="${SUDO_USER:-$(whoami)}"

VENV_DIR="${APP_DIR}/.venv"          # Python 虚拟环境目录（项目的“独立小房间”）
LOG_DIR="${APP_DIR}/logs"            # 日志目录
ENV_FILE="${APP_DIR}/.env"           # 环境变量配置文件
SERVICE_FILE="/etc/systemd/system/${APP_NAME}.service"  # systemd 服务定义文件路径

# ------------------------------ 小工具函数 -----------------------------------
# 带颜色的日志输出，方便在满屏文字中一眼看到关键步骤。
log()  { echo -e "\033[1;32m[MODEX]\033[0m $*"; }
warn() { echo -e "\033[1;33m[MODEX][警告]\033[0m $*"; }
err()  { echo -e "\033[1;31m[MODEX][错误]\033[0m $*" >&2; }

# ------------------------------ 前置检查 -------------------------------------
# systemd 注册、防火墙配置等需要 root 权限，所以整脚本要求用 sudo 执行。
if [[ "$(id -u)" -ne 0 ]]; then
    err "请使用 root 权限运行：sudo bash deploy.sh"
    exit 1
fi

if [[ ! -f "${APP_DIR}/requirements.txt" ]]; then
    err "未在 ${APP_DIR} 找到 requirements.txt，请确认脚本位于项目根目录。"
    exit 1
fi

MODE="${1:-install}"   # 第一个参数决定模式：install(默认) / update / restart

# ------------------------- 模式：仅重启服务 -----------------------------------
if [[ "${MODE}" == "restart" ]]; then
    log "重启 ${APP_NAME} 服务..."
    systemctl restart "${APP_NAME}"
    systemctl status "${APP_NAME}" --no-pager
    exit 0
fi

# =============================================================================
# 步骤 1：安装系统依赖（Python3、venv、pip 等）
# =============================================================================
install_system_deps() {
    log "步骤 1/6：安装系统依赖..."
    if command -v apt-get >/dev/null 2>&1; then
        apt-get update -y
        apt-get install -y python3 python3-venv python3-pip curl
    elif command -v dnf >/dev/null 2>&1; then
        dnf install -y python3 python3-pip curl
    elif command -v yum >/dev/null 2>&1; then
        yum install -y python3 python3-pip curl
    else
        err "未识别的包管理器（既非 apt 也非 dnf/yum），请手动安装 python3/venv/pip。"
        exit 1
    fi

    # 校验 Python 版本 >= 3.10（项目使用 Pydantic v2，对版本有要求）
    local py_ver
    py_ver="$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')"
    log "检测到 Python 版本：${py_ver}"
    python3 - <<'PYEOF'
import sys
if sys.version_info < (3, 10):
    raise SystemExit("需要 Python >= 3.10，请升级系统 Python 后重试。")
PYEOF
}

# =============================================================================
# 步骤 2：创建虚拟环境并安装 Python 依赖
# =============================================================================
install_python_deps() {
    log "步骤 2/6：创建虚拟环境并安装依赖..."

    # 虚拟环境已存在则复用，避免每次部署都重建（幂等：重复执行结果一致）
    if [[ ! -d "${VENV_DIR}" ]]; then
        python3 -m venv "${VENV_DIR}"
    fi

    # 用虚拟环境里自己的 pip 安装依赖，不污染系统 Python
    "${VENV_DIR}/bin/pip" install --upgrade pip
    "${VENV_DIR}/bin/pip" install -r "${APP_DIR}/requirements.txt"
    "${VENV_DIR}/bin/pip" install gunicorn   # 生产环境的进程管理器（uvicorn 的“车间主任”）
}

# =============================================================================
# 步骤 3：检查 .env 配置
# =============================================================================
check_env_file() {
    log "步骤 3/6：检查环境变量配置..."

    # .env 不存在时，从模板复制一份，并停下来提醒用户填写密钥——
    # 类比：新房钥匙没配好，先别急着入住。
    if [[ ! -f "${ENV_FILE}" ]]; then
        cp "${APP_DIR}/.env.example" "${ENV_FILE}"
        warn "已根据 .env.example 生成 ${ENV_FILE}"
        warn "请先编辑该文件，填入各家模型厂商的 API Key，然后重新运行本脚本。"
        warn "编辑命令：vim ${ENV_FILE}"
        exit 0
    fi

    # 简单提示哪些 Key 还是空的（不强制退出，因为可能只用到部分厂商）
    for key in DEEPSEEK_API_KEY MOONSHOT_API_KEY QWEN_API_KEY ZHIPU_API_KEY ROUTER_API_KEY; do
        if ! grep -qE "^${key}=.+" "${ENV_FILE}"; then
            warn "${key} 为空，对应厂商的模型路由将调用失败（不影响其他厂商）。"
        fi
    done
}

# =============================================================================
# 步骤 4：准备日志目录并修正文件归属
# =============================================================================
prepare_dirs() {
    log "步骤 4/6：准备日志目录与文件权限..."
    mkdir -p "${LOG_DIR}"
    # 把整个项目目录的所有者改为运行用户，保证服务进程能读写日志与 .env
    chown -R "${SERVICE_USER}:${SERVICE_USER}" "${APP_DIR}"
}

# =============================================================================
# 步骤 5：注册 systemd 服务（开机自启 + 崩溃自动拉起）
# =============================================================================
register_service() {
    log "步骤 5/6：注册 systemd 服务 ${APP_NAME}..."

    # 用 heredoc 生成服务定义文件。关键字段说明：
    #   WorkingDirectory : 服务的工作目录，保证能读到项目根目录的 .env
    #   ExecStart        : 用虚拟环境里的 gunicorn 启动，-k 指定 uvicorn worker 运行 ASGI
    #   Restart=always   : 进程意外退出时自动重启（“管家”职责）
    cat > "${SERVICE_FILE}" <<EOF
[Unit]
Description=MODEX AI Backend
After=network.target

[Service]
User=${SERVICE_USER}
WorkingDirectory=${APP_DIR}
ExecStart=${VENV_DIR}/bin/gunicorn app.main:app \
    -k uvicorn.workers.UvicornWorker \
    -w ${WORKERS} \
    -b 0.0.0.0:${PORT} \
    --access-logfile ${LOG_DIR}/access.log \
    --error-logfile ${LOG_DIR}/error.log \
    --timeout 120
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
EOF

    systemctl daemon-reload            # 让 systemd 重新读取服务定义
    systemctl enable "${APP_NAME}"     # 设置开机自启
}

# =============================================================================
# 步骤 6：启动服务并做健康检查
# =============================================================================
start_and_verify() {
    log "步骤 6/6：启动服务并健康检查..."
    systemctl restart "${APP_NAME}"

    # 最多等待 10 秒，反复探测 /docs 页面，确认服务真正起来了
    local ok=false
    for _ in $(seq 1 10); do
        if curl -sf "http://127.0.0.1:${PORT}/docs" >/dev/null 2>&1; then
            ok=true
            break
        fi
        sleep 1
    done

    if [[ "${ok}" == "true" ]]; then
        log "部署成功！服务已在端口 ${PORT} 运行。"
        log "常用命令："
        echo "  查看状态：sudo systemctl status ${APP_NAME}"
        echo "  查看日志：sudo journalctl -u ${APP_NAME} -f"
        echo "  接口文档：http://<服务器IP>:${PORT}/docs"
    else
        err "服务未在预期时间内响应，请查看日志排查：sudo journalctl -u ${APP_NAME} -n 50"
        exit 1
    fi
}

# =============================================================================
# 主流程：update 模式跳过系统依赖安装，其余与首次部署一致
# =============================================================================
if [[ "${MODE}" == "update" ]]; then
    log "更新模式：重装依赖并重启服务..."
    install_python_deps
    prepare_dirs
    start_and_verify
else
    log "开始首次部署（安装目录：${APP_DIR}，运行用户：${SERVICE_USER}）..."
    install_system_deps
    install_python_deps
    check_env_file
    prepare_dirs
    register_service
    start_and_verify
fi
