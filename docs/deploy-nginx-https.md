# 反向代理 + HTTPS 部署（nginx + Let's Encrypt）

面向「一台 Linux 服务器上跑 docker compose，前面加 nginx 终结 TLS」的部署方式。
配置模板在同目录的 [`deploy/nginx/`](../deploy/nginx/)。

> 本文命令均在 Alibaba Cloud Linux 3（el8 体系）+ nginx 1.24 + certbot 1.22 上实测通过。
> 示例域名用 `www.example.com`，替换成你自己的。

---

## 前置条件

1. **域名已解析到服务器**（A 记录），且服务器安全组放行 **80 和 443**。
2. **域名已完成 ICP 备案**（服务器在大陆节点时）。这不是走过场：未备案的域名访问大陆节点的
   80 端口会被阿里云拦掉，返回一张 `Non-compliance ICP Filing` 的拦截页，**而不是你的站点**。
   这个拦截会连带让 Let's Encrypt 的 HTTP-01 校验失败，表现为 certbot 报
   `Invalid response from http://xxx: 403`，看起来像配置问题，实际是备案问题。
   （实测 443 端口此时不被拦，但不建议靠这个绕过备案。）
3. 服务器上已装好 docker + docker compose，且本项目的容器能正常起来。

---

## 步骤

### 1. 让前端容器退到回环地址

前端容器默认绑 `0.0.0.0:80`，会和 nginx 抢 80 端口。在项目根目录的 `.env` 里加一行：

```bash
FRONTEND_BIND=127.0.0.1:3000
```

然后重建前端容器：

```bash
docker compose up -d frontend
```

验证：`ss -ltn | grep 3000` 应该显示 `127.0.0.1:3000` 而不是 `0.0.0.0:80`。

### 2. 安装 nginx 与 certbot

```bash
dnf install -y nginx certbot
```

> certbot 用来签发和续期证书。发行版仓库里的版本通常偏旧（本篇是 1.22），
> 但 webroot 模式签发/续期完全够用。

### 3. 放置配置文件

```bash
mkdir -p /etc/nginx/snippets /var/www/certbot

cp deploy/nginx/parse_video_proxy.conf    /etc/nginx/snippets/
sed 's/__DOMAIN__/www.example.com/g' \
    deploy/nginx/parse_video.conf.template > /etc/nginx/conf.d/parse_video.conf
```

### 4. 注释掉发行版自带的默认站点

nginx 包会自带一个 `server { listen 80; server_name _; root /usr/share/nginx/html; }`，
它是 80 的 `default_server`。不处理的话有两个问题：我们的配置里再写 `default_server`
会导致 nginx 起不来；就算不写，用 IP 访问也会落到 nginx 欢迎页而不是应用。

该块在 `/etc/nginx/nginx.conf` 里（el8 系通常在 37–53 行）。**先 diff 确认行号再改**：

```bash
cp /etc/nginx/nginx.conf /etc/nginx/nginx.conf.bak
sed -n '30,60p' /etc/nginx/nginx.conf     # 确认 server 块的实际行号
sed -i '37,53 s/^/#/' /etc/nginx/nginx.conf
```

### 5. 校验并启动

```bash
nginx -t
systemctl enable --now nginx
```

此时访问 `http://<域名>/login` 应该已经能看到应用（还没 HTTPS）。

### 6. 签发证书前先自检校验路径

这一步能省掉一次无谓的失败尝试（Let's Encrypt 对同一域名每小时只允许 5 次失败）：

```bash
echo "acme-path-ok" > /var/www/certbot/.well-known/acme-challenge/testfile
curl -s http://www.example.com/.well-known/acme-challenge/testfile   # 应回显 acme-path-ok
rm -f /var/www/certbot/.well-known/acme-challenge/testfile
```

### 7. 签发证书

```bash
certbot certonly --webroot -w /var/www/certbot -d www.example.com \
  --non-interactive --agree-tos -m you@example.com --no-eff-email
```

证书落在 `/etc/letsencrypt/live/www.example.com/`。**这一步必须在 nginx 已经接管 80
之后做**——HTTP-01 校验需要 `/.well-known/acme-challenge/` 能被公网访问到。

### 8. 补上续期后重载 nginx 的钩子

```bash
CONF=/etc/letsencrypt/renewal/www.example.com.conf
grep -q renew_hook "$CONF" || sed -i "/^\[renewalparams\]/a renew_hook = systemctl reload nginx" "$CONF"
```

### 9. 把续期定时器拉起来（⚠️ 必做）

**certbot 装的 `certbot-renew.timer` 装完是 `enabled` 但 `inactive`** —— 开机不会跑、
当前也没在跑。不管它的话，证书 90 天后**静默过期**，HTTPS 直接断且没有任何提示：

```bash
systemctl daemon-reload
systemctl start certbot-renew.timer
systemctl list-timers | grep certbot          # 确认有 NEXT 触发时间
```

### 10. 更新后端配置里的域名

`.env` 里这两项改成 https 域名，然后重启后端：

```bash
FRONTEND_HOST=https://www.example.com
BACKEND_CORS_ORIGINS="https://www.example.com,http://www.example.com"
```

```bash
docker compose up -d backend
```

---

## 验证清单

```bash
# 本地
ss -ltn | grep -E ':80 |:443 |:3000 '            # nginx 占 80/443，容器在 127.0.0.1:3000
nginx -t
systemctl list-timers | grep certbot             # 续期定时器 active

# 公网（重要：一定要从外网测，本机 hosts 或代理会掩盖问题）
curl -sI http://www.example.com/login            # 301 → https
curl -s -o /dev/null -w "%{http_code}\n" https://www.example.com/login          # 200
curl -s -o /dev/null -w "%{http_code}\n" https://www.example.com/api/v1/videos  # 401（鉴权拦截，说明链路通）
curl -s -o /dev/null -w "cert=%{ssl_verify_result}\n" https://www.example.com/  # 0 = 证书可信

# 续期演练（用 staging，不会消耗正式配额）
certbot renew --dry-run
```

---

## 踩坑记录

### 1. `client_max_body_size` 不放开，视频上传全部 413

nginx 默认只允许 **1MB** 请求体，而本项目后端允许 **200MB** 视频。不设这个参数时，
上传大视频会直接被 nginx 拒掉，现象是"点了上传没反应/报错"，而且**后端日志里什么都看不到**
（请求根本没到后端）。模板里已设为 `500m`。

### 2. `certbot-renew.timer` 装完是 `inactive`

见上面第 9 步。这是最隐蔽的一个坑：签发当天一切正常，90 天后突然访问不了，
而期间没有任何告警。部署完务必 `systemctl list-timers | grep certbot` 确认一次。

### 3. 前端容器和 nginx 抢 80

`docker-compose.yml` 里前端默认 `0.0.0.0:80`。前面加了 nginx 之后，两者都要占 80，
容器会起不来（`port is already allocated`）。用 `.env` 里的 `FRONTEND_BIND` 让容器退回
`127.0.0.1:3000`。

### 4. 备案未完成时，certbot 会以"403"的形式失败

未备案域名在大陆节点会被拦在 80 端口，返回阿里云的备案阻断页。此时 certbot 报的是
`Invalid response from http://xxx/.well-known/acme-challenge/yyy: 403`，很容易被误判成
文件权限或 nginx 配置问题。**先确认域名是否已备案**，再看 nginx。

顺带一提：不要只从服务器本机 `curl 127.0.0.1` 验证——备案拦截发生在阿里云的网关层，
本机访问永远正常，必须从公网测。

### 5. 系统自带的默认 server 块

见上面第 4 步。症状是用 IP 访问时看到的是 nginx 的欢迎页而不是应用。
