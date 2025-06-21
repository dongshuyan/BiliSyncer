# BiliSyncer

🎯 **智能的B站内容同步工具** - 批量下载、断点续传、增量更新

[![Python](https://img.shields.io/badge/Python-3.8%2B-blue.svg)](https://python.org)
[![License](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![WebUI](https://img.shields.io/badge/WebUI-Available-brightgreen.svg)](webui)

## 🌟 项目简介

BiliSyncer 是一个专业的B站内容同步工具，专注于批量下载和智能管理。基于 `yutto` 构建，提供完整的批量下载解决方案，支持断点续传、增量更新和Web界面管理。

## ✨ 核心特性

### 📺 全面的内容支持
- **投稿视频** - 支持单个视频或完整系列
- **番剧电影** - 自动获取所有集数
- **收藏夹** - 批量下载收藏内容
- **用户空间** - UP主全部作品
- **课程内容** - B站付费课程
- **视频合集** - 完整的视频系列

### 🔄 智能同步机制
- **断点续传** - 自动恢复中断的下载
- **增量更新** - 只下载新增内容
- **状态跟踪** - CSV文件管理下载状态
- **批量更新** - 一键更新所有任务

### 🎨 用户体验
- **Web界面** - 直观的图形化操作
- **实时监控** - 下载进度实时显示
- **配置管理** - 灵活的YAML配置系统
- **多平台支持** - 跨平台兼容

## 🚀 快速开始

### 环境要求

- Python 3.8+
- yutto (原版B站下载工具)

### 安装部署

```bash
# 1. 安装依赖
pip install yutto
pip install -r requirements.txt

# 2. 启动Web界面
python start_webui.py

# 3. 或使用命令行
python main.py "https://www.bilibili.com/video/BV1xx411c7mD"
```

### 基本使用

#### Web界面
访问 `http://localhost:端口` 使用图形化界面进行批量下载和管理。

#### 命令行界面
```bash
# 下载单个视频
python main.py "https://www.bilibili.com/video/BV1xx411c7mD"

# 下载收藏夹
python main.py "https://space.bilibili.com/123456/favlist?fid=789012" -c "SESSDATA"

# 批量更新所有任务
python main.py --update -o "/path/to/downloads" -c "SESSDATA"

# 使用配置文件
python main.py "URL" --config default
```

## 📁 项目结构

```
BiliSyncer/
├── main.py              # 命令行入口
├── start_webui.py       # Web界面启动器
├── batch_downloader.py  # 批量下载引擎
├── extractors.py        # URL解析器
├── config/              # 配置文件
│   ├── default.yaml     # 默认配置
│   └── vip.yaml         # VIP配置示例
├── utils/               # 工具模块
│   ├── csv_manager.py   # 状态管理
│   ├── logger.py        # 日志系统
│   └── config_manager.py # 配置管理
├── webui/               # Web界面
│   ├── app.py           # Flask应用
│   ├── templates/       # 模板文件
│   └── static/          # 静态资源
└── api/                 # API接口
    └── bilibili.py      # B站API
```

## 🔧 配置说明

### 配置文件格式
```yaml
name: "配置名称"
description: "配置描述"
output_dir: "~/Downloads"
sessdata: "your_sessdata_here"
vip_strict: true
debug: false
extra_args: ["--quality", "8K"]
```

### 获取SESSDATA
1. 登录 bilibili.com
2. 打开开发者工具 (F12)
3. 转到 Application → Cookies
4. 复制 `SESSDATA` 的值

## 🎯 使用场景

- **内容创作者** - 备份自己的作品
- **学习资料** - 下载课程和教程
- **收藏管理** - 批量下载收藏夹内容
- **追番追剧** - 自动更新番剧内容
- **资料整理** - 系统化管理视频资源

## 🔄 更新机制

BiliSyncer 的智能更新机制：
1. **状态检测** - 扫描已下载内容
2. **内容对比** - 检查是否有新增视频
3. **增量下载** - 只下载新的内容
4. **状态同步** - 更新下载记录

## 🛠️ 技术栈

- **核心** - Python 3.8+
- **下载引擎** - yutto
- **Web框架** - Flask + SocketIO
- **前端** - Bootstrap 5
- **配置管理** - PyYAML
- **异步处理** - asyncio

## 📊 性能特点

- **并发处理** - 支持多任务并行
- **内存优化** - 低内存占用
- **网络优化** - 智能重试机制
- **存储优化** - 避免重复下载

## 🤝 贡献指南

欢迎提交Issue和Pull Request。请确保：
- 遵循现有代码风格
- 添加适当的测试
- 更新相关文档

## 📜 许可证

本项目采用 MIT 许可证。详见 [LICENSE](LICENSE) 文件。

## 🙋‍♂️ 支持与反馈

如有问题或建议，请通过以下方式联系：
- 提交 [Issue](issues)
- 发起 [Discussion](discussions)

---

⭐ 如果这个项目对你有帮助，请给个Star支持一下！ 