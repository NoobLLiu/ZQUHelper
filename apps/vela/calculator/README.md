# Vela 快应用：计算器

目标设备：**小米手环 10 NFC**。基于官方 **AIoT-toolkit 2.0**（`aiot` CLI），可脱离 AIoT-IDE 用命令行构建，也支持在 AIoT-IDE 中打开调试。

## 目录（AIoT-toolkit 2.0 结构）

```
calculator/
├── package.json           # scripts: build / release / start，devDependencies 含 aiot-toolkit
├── .npmrc                 # npmmirror 镜像
├── sign/                  # 发布签名（private.pem / certificate.pem，已被 git 忽略）
└── src/
    ├── manifest.json      # 应用信息 / 路由 / deviceTypeList: ["watch"] / 图标
    ├── assets/icon.png    # 应用图标
    ├── app.ux
    └── pages/index/index.ux   # 计算器页面
```

## 命令行构建

```bash
npm install        # 安装 aiot-toolkit
npm run build      # 生成 dist/*.debug.rpk（调试包，工具链内置调试签名）
npm run release    # 发布包，需 sign/ 下有正式签名
```

- 每次提交 GitHub Actions 会自动构建 rpk 并上传为 artifact（`.github/workflows/ci.yml` 的 `vela` job）。

## 用 AIoT-IDE 调试

1. 下载安装 [AIoT-IDE](https://iot.mi.com/vela/quickapp/zh/guide/start/use-ide.html)（Windows 版）。
2. 「文件」→「打开项目」，选择 `apps/vela/calculator` 目录。
3. 按右侧开发向导提示安装依赖（若 `npm i` 失败，项目内已带 `.npmrc` 指向 npmmirror）。
4. 模拟器：若缺少环境，点向导里的「检查模拟器环境，创建模拟器实例」→「自动安装」，再创建一个 watch 模拟器实例。
5. 点顶部 banner 的「运行/调试」按钮，在模拟器中启动计算器；底部调试面板可看 DOM、Console、断点。

## 真机（手环 10 NFC）

- 开发调试：按 Vela 官方文档开启手环开发者模式后通过调试通道安装 `.debug.rpk`。
- 发布打包：点「发布」自动生成签名（需本机安装 openssl；Windows 缺失时需自行安装并配好环境变量，或用命令手动生成到 `sign/`）：
  `openssl req -newkey rsa:2048 -nodes -keyout private.pem -x509 -days 3650 -out certificate.pem`
- 打包产物在 `dist/` 下（`.rpk`），`dist/`、`build/`、签名文件均不入库。

## 备注

- `manifest.json` 中 `designWidth` 按 212（手环 10 屏宽）设置；若 IDE/模拟器提示与实际设备不符，以其向导值为准微调。
- 页面布局使用 flex + 相对尺寸，适配小圆屏；后续新增手环端工具页可直接复用本工程并在 `router.pages` 里追加。
