# BiliSyncer

🎯 **Intelligent Bilibili Content Synchronization Tool** - Batch download, resume support, and incremental updates

[![Python](https://img.shields.io/badge/Python-3.8%2B-blue.svg)](https://python.org)
[![License](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![WebUI](https://img.shields.io/badge/WebUI-Available-brightgreen.svg)](webui)

[🇨🇳 中文文档](README_ZH.md) | 🇺🇸 English

## 🌟 Overview

BiliSyncer is a professional Bilibili content management tool that extends yutto with advanced batch downloading, intelligent synchronization, and web-based management capabilities. Perfect for content creators, educators, and media enthusiasts who need systematic content management.

## ✨ Key Features

### 🔄 Intelligent Sync System
- **Batch Downloads** - Process multiple URLs simultaneously
- **Resume Support** - Automatically resume interrupted downloads
- **Incremental Updates** - Download only new content since last sync
- **Smart Status Tracking** - CSV-based progress management

### 📺 Comprehensive Content Support
- User videos & series | Anime & movies | Favorites & collections
- User spaces | Courses | Playlists | Watch later

### 🎨 Modern Web Interface
- Real-time progress monitoring | Task management dashboard
- Configuration management | One-click batch operations

### 🛡️ Robust & Reliable
- Advanced retry mechanisms | Network error handling
- Force stop capabilities | Cross-platform compatibility

## 🆚 BiliSyncer vs Yutto vs Yutto-uiya

| Feature | BiliSyncer | Yutto | Yutto-uiya |
|---------|------------|-------|------------|
| **Core Purpose** | Batch sync & management | Versatile CLI downloader | Simple WebUI wrapper |
| **Interface Type** | Professional Web Dashboard | Powerful Command Line | User-friendly Streamlit UI |
| **Download Engine** | Built on yutto | Original robust engine | Built on yutto |
| **Batch Operations** | ✅ Multi-task management | ✅ Batch download support | ✅ Basic batch support |
| **Resume Downloads** | ✅ Automatic detection | ✅ Built-in resume capability | ✅ Inherits yutto's resume |
| **Incremental Updates** | ✅ Smart sync detection | ➖ Manual re-execution | ➖ Manual re-execution |
| **Status Persistence** | ✅ CSV-based tracking | ➖ Session-based only | ➖ Session-based only |
| **Configuration** | ✅ Web + YAML management | ✅ Rich CLI options | ✅ Simple web forms |
| **Content Organization** | ✅ Structured folder naming | ✅ Flexible path templates | ✅ Basic organization |
| **Performance** | ⚠️ Web overhead | ✅ Lightweight & fast | ⚠️ Streamlit overhead |
| **Extensibility** | ⚠️ Web-focused architecture | ✅ Highly modular design | ⚠️ UI-focused |
| **Learning Curve** | 🟢 Beginner-friendly | 🟡 Technical users | 🟢 Very easy |
| **Use Case** | Content management | Power user downloads | Casual downloading |

### 🎯 Each Tool's Strength

**Yutto**: The robust foundation - powerful, fast, and highly configurable CLI tool perfect for technical users who need maximum control and performance.

**Yutto-uiya**: The accessibility bridge - brings yutto's power to casual users through a clean, simple web interface without complexity.

**BiliSyncer**: The management layer - adds enterprise-level batch management, sync intelligence, and persistent tracking for systematic content organization.

## 📱 Interface Preview

### Download Management
![Download Management](pictures/example-1.png)

### Batch Updates
![Batch Updates](pictures/example-2.png)

### Task Status
![Task Status](pictures/example-3.png)

### Configuration Management
![Configuration Management](pictures/example-4.png)

## 🚀 Quick Start

### Prerequisites
```bash
# Install dependencies
pip install yutto
pip install -r requirements.txt
```

### Launch Web Interface
```bash
python start_webui.py
# Visit http://localhost:5000
```

### Command Line Usage
```bash
# Single download
python main.py "https://www.bilibili.com/video/BV1xx411c7mD"

# Batch update all configured tasks
python main.py --update -c "SESSDATA"

# Use custom configuration
python main.py "URL" --config vip
```

## 🔧 Configuration

Create `config/your_config.yaml`:
```yaml
name: "My Config"
output_dir: "~/Downloads"
sessdata: "your_sessdata_here"
vip_strict: true
extra_args: ["--quality", "8K"]
```

**Getting SESSDATA**: Login to bilibili.com → F12 → Application → Cookies → Copy `SESSDATA` value

## 🎯 Perfect For

- **Content Creators** - Backup and organize your content library
- **Educators** - Download course materials and educational content
- **Media Collectors** - Systematically manage anime, series, and favorites
- **Researchers** - Batch download reference materials

## 🛠️ Tech Stack

Built with Python 3.8+, Flask, yutto, and modern web technologies for reliability and performance.

## 🤝 Contributing

We welcome contributions! Submit Issues or Pull Requests to help improve BiliSyncer.

## 📜 License

MIT Licensed - see [LICENSE](LICENSE) for details.

---

⭐ **Star this project if it helps you manage your Bilibili content!** 