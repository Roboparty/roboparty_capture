# EGO SDK 原始归档

此目录暂随 Git 保存用户提供的 EGO 配套 OrbbecSDK 2.9.0 Linux x86_64 与 ARM64 原始 `.tar.gz`，不包含 Viewer 或其他平台包，不重新打包或修改厂商内容。

版本、归档目录名及 SHA256 统一维护在 [sdk_manifest.json](../../scripts/sdk_manifest.json)。仓库根目录运行：

```bash
/usr/bin/python3 scripts/setup_sdk.py
```

安装器自动选择本机架构，校验归档后解压到被 Git 忽略的 `.local/ego-sdk/`。更换架构需要在目标机器重新安装、编译；ARM64 包存在不代表已经完成板端测试。

厂商 SDK 的授权以归档内附带的条款为准，项目自身许可证不替代 SDK 条款。
