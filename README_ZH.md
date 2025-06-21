# BiliSyncer

🎯 **智能的B站内容同步工具** - 批量下载、断点续传、增量更新

[![Python](https://img.shields.io/badge/Python-3.8%2B-blue.svg)](https://python.org)
[![License](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![WebUI](https://img.shields.io/badge/WebUI-Available-brightgreen.svg)](webui)

🇨🇳 中文 | [🇺🇸 English](README.md)

## 🌟 项目简介

BiliSyncer 是一个专业的B站内容管理工具，在 yutto 基础上扩展了先进的批量下载、智能同步和Web管理功能。完美适合内容创作者、教育工作者和媒体爱好者进行系统化内容管理。

## ✨ 核心特性

### 🔄 智能同步系统
- **批量下载** - 同时处理多个URL
- **断点续传** - 自动恢复中断的下载
- **增量更新** - 仅下载上次同步后的新内容
- **智能状态跟踪** - CSV文件管理进度

### 📺 全面内容支持
- 投稿视频&系列 | 番剧&电影 | 收藏夹&合集
- 用户空间 | 课程 | 播放列表 | 稍后再看

### 🎨 现代Web界面
- 实时进度监控 | 任务管理面板
- 配置管理 | 一键批量操作

### 🛡️ 稳定可靠
- 高级重试机制 | 网络错误处理
- 强制停止功能 | 跨平台兼容

## 🆚 BiliSyncer vs Yutto vs Yutto-uiya

| 功能特性 | BiliSyncer | Yutto | Yutto-uiya |
|---------|------------|-------|------------|
| **核心定位** | 批量同步&管理 | 强大的CLI下载器 | 简单的网页封装 |
| **界面类型** | 专业Web仪表板 | 强大命令行界面 | 友好的Streamlit界面 |
| **下载引擎** | 基于yutto构建 | 原创强大引擎 | 基于yutto构建 |
| **批量操作** | ✅ 多任务管理 | ✅ 批量下载支持 | ✅ 基础批量支持 |
| **断点续传** | ✅ 自动检测恢复 | ✅ 内置续传功能 | ✅ 继承yutto续传 |
| **增量更新** | ✅ 智能同步检测 | ➖ 需手动重新执行 | ➖ 需手动重新执行 |
| **状态持久化** | ✅ CSV文件跟踪 | ➖ 仅会话状态 | ➖ 仅会话状态 |
| **配置管理** | ✅ Web + YAML管理 | ✅ 丰富CLI选项 | ✅ 简单网页表单 |
| **内容组织** | ✅ 结构化文件夹命名 | ✅ 灵活路径模板 | ✅ 基础组织方式 |
| **性能表现** | ⚠️ Web服务开销 | ✅ 轻量高效 | ⚠️ Streamlit开销 |
| **扩展性** | ⚠️ Web架构局限 | ✅ 高度模块化设计 | ⚠️ UI功能局限 |
| **学习曲线** | 🟢 新手友好 | 🟡 技术用户 | 🟢 非常简单 |
| **适用场景** | 内容系统管理 | 专业用户下载 | 休闲下载使用 |

### 🎯 各工具特色

**Yutto**: 强大基础 - 高性能、高可配置的CLI工具，为技术用户提供最大控制力和性能。

**Yutto-uiya**: 易用桥梁 - 通过简洁的Web界面将yutto的强大功能带给普通用户，无需复杂配置。

**BiliSyncer**: 管理层面 - 添加企业级批量管理、同步智能和持久跟踪，用于系统化内容组织。

## 📱 界面预览

### 下载管理
![下载管理](pictures/example-1.png)

### 批量更新
![批量更新](pictures/example-2.png)

### 任务状态
![任务状态](pictures/example-3.png)

### 配置管理
![配置管理](pictures/example-4.png)

## 🚀 快速开始

### 环境准备
```bash
# 安装依赖
pip install yutto
pip install -r requirements.txt
```

### 启动Web界面
```bash
python start_webui.py
# 访问 http://localhost:5000
```

### 命令行使用
```bash
# 单次下载
python main.py "https://www.bilibili.com/video/BV1xx411c7mD"

# 带附加选项
python main.py "URL" --vip-strict --save-cover

# 批量更新所有配置任务
python main.py --update -c "SESSDATA"

# 使用自定义配置
python main.py "URL" --config vip
```

## 🔧 配置说明

创建 `config/your_config.yaml`：
```yaml
name: "我的配置"
output_dir: "~/Downloads"
sessdata: "your_sessdata_here"
vip_strict: true
save_cover: true
extra_args: ["--quality", "8K"]
```

**获取SESSDATA**：登录 bilibili.com → F12 → Application → Cookies → 复制 `SESSDATA` 值

## 🎯 适用场景

- **内容创作者** - 备份和整理内容库
- **教育工作者** - 下载课程资料和教育内容
- **媒体收藏者** - 系统化管理番剧、剧集和收藏
- **研究人员** - 批量下载参考资料

## 🛠️ 技术栈

基于 Python 3.8+、Flask、yutto 和现代Web技术构建，确保可靠性和性能。

## 🤝 贡献指南

欢迎贡献！提交 Issues 或 Pull Requests 来帮助改进 BiliSyncer。

## 📜 许可证

MIT 许可证 - 详见 [LICENSE](LICENSE) 文件。

---

⭐ **如果这个项目帮助你管理B站内容，请给个Star支持！** 