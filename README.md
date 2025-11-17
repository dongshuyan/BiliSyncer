<div align="center">
  <img src="pictures/Logo.png" alt="BiliSyncer Logo" width="200">
  
  # BiliSyncer

  🎯 **Intelligent Bilibili Content Synchronization Tool** - Automated sync management, incremental updates, and batch downloads
</div>

[![Python](https://img.shields.io/badge/Python-3.8%2B-blue.svg)](https://python.org)
[![License](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![WebUI](https://img.shields.io/badge/WebUI-Available-brightgreen.svg)](webui)

[🇨🇳 中文文档](README_ZH.md) | 🇺🇸 English

## 🌟 Overview

BiliSyncer is an intelligent synchronization management tool specifically designed for continuously updating Bilibili content. It focuses on solving the automated synchronization challenges of user favorites, UP master uploads, anime series, and other continuously updating resources. Built upon yutto, it provides a complete resource management ecosystem that makes content management simple and efficient.

## ✨ Core Advantages

### 🎯 Intelligent Resource Discovery & Recognition
- **Precise Resource Targeting** - Automatically retrieves complete and accurate video lists from favorites, UP master uploads, etc., without omissions or redundancy
- **Smart Update Detection** - Automatically identifies all new content since the last sync, avoiding redundant requests and invalid operations
- **Comprehensive Content Support** - Full support for user videos, anime, movies, courses, favorites, collections, and more

### 🔄 Advanced Synchronization Management
- **Incremental Sync Technology** - Only synchronizes new and changed content, dramatically saving time and bandwidth
- **Resume Protection** - Automatically recovers from network interruptions or unexpected stops, ensuring download continuity
- **Persistent Status Tracking** - CSV-based progress management ensures sync records are never lost

### 🧹 One-Click Cleanup & Space Management
- **Smart Cleanup Function** - Supports one-click cleanup of all downloaded files after backup completion, freeing storage space
- **Record Retention Mechanism** - Preserves complete download records while cleaning files, providing foundation for future incremental syncs
- **Storage Optimization Strategy** - Flexible file management strategies adapted to different storage scenarios

### ⚙️ Versatile Configuration Management
- **Multi-Account Support** - Supports independent configuration and management of multiple Bilibili accounts for different permission needs
- **Differentiated Configuration** - Provides independent parameter configuration schemes for different download requirements
- **Configuration Templating** - Preset common configuration templates for quick application to different task scenarios

### 📊 Visual Monitoring & Analytics
- **Real-Time Task Monitoring** - Intuitively displays execution status and progress information of all sync tasks
- **Historical Record Analysis** - Automatically tracks sync history and provides detailed task execution reports
- **Resource Status Overview** - At-a-glance view of sync status and storage information for all resources

### 🔧 Granular Task Scheduling
- **Concurrent Task Management** - Supports parallel execution of multiple tasks, maximizing system resource utilization
- **Task Lifecycle Control** - Provides complete control functions for task start, pause, stop, restart, etc.
- **Priority Scheduling** - Supports task priority settings to prioritize important resources

### 🎨 Intuitive & User-Friendly Web Interface
- **Modern Design** - Clean and beautiful responsive web interface adapted to various devices
- **Operational Simplicity** - Intuitive operation flow reduces learning costs and enhances user experience
- **Feature Integration** - All management functions centralized in a unified interface, avoiding complex command-line operations

### ⚡ Efficient Command Line Interface
- **Batch Processing Capability** - Powerful CLI support for easy script invocation and automation integration
- **Parameter Flexibility** - Rich command-line parameters meeting advanced users' fine-grained control needs
- **Program Integration Friendly** - Easy integration into other automation systems and workflows

## 🆚 BiliSyncer vs Yutto vs Yutto-uiya

| Feature | BiliSyncer | Yutto | Yutto-uiya |
|---------|------------|-------|------------|
| **Core Purpose** | Continuous sync management | Versatile CLI downloader | Simple WebUI wrapper |
| **Sync Capability** | ✅ Smart incremental sync | ➖ Manual re-execution required | ➖ Manual re-execution required |
| **Resource Management** | ✅ Complete lifecycle management | ➖ Download-only functionality | ➖ Download-only functionality |
| **Interface Type** | Professional Web Dashboard | Powerful Command Line | User-friendly Streamlit UI |
| **Download Engine** | Built on yutto | Original robust engine | Built on yutto |
| **Batch Operations** | ✅ Multi-task management | ✅ Batch download support | ✅ Basic batch support |
| **Resume Downloads** | ✅ Automatic detection | ✅ Built-in resume capability | ✅ Inherits yutto's resume |
| **Status Persistence** | ✅ CSV-based tracking | ➖ Session-based only | ➖ Session-based only |
| **Configuration** | ✅ Web + YAML management | ✅ Rich CLI options | ✅ Simple web forms |
| **Content Organization** | ✅ Structured folder naming | ✅ Flexible path templates | ✅ Basic organization |
| **Learning Curve** | 🟢 Beginner-friendly | 🟡 Technical users | 🟢 Very easy |
| **Use Case** | Continuous content management | Power user downloads | Casual downloading |

### 🎯 Each Tool's Strength

**Yutto**: The robust foundation - powerful, fast, and highly configurable CLI tool perfect for technical users who need maximum control and performance.

**Yutto-uiya**: The accessibility bridge - brings yutto's power to casual users through a clean, simple web interface without complexity.

**BiliSyncer**: The management layer - focuses on automated synchronization management of continuously updating content, providing complete resource lifecycle solutions.

## 📱 Interface Preview

### Download Management Interface
![Download Management](pictures/p1.png)

### Batch Update Interface
![Batch Updates 1](pictures/p2-1.png)
![Batch Updates 2](pictures/p2-2.png)

### Task Status Interface
![Task Status](pictures/p3.png)

### Configuration Management Interface
![Configuration Management](pictures/p4.png)

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

# With additional options
python main.py "URL" --vip-strict --save-cover

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
save_cover: true
extra_args: ["--quality", "8K"]
```

**Getting SESSDATA**: Login to bilibili.com → F12 → Application → Cookies → Copy `SESSDATA` value

## 🛠️ Utility Tools

### Directory Size Analysis Tool

`tools/dir_tree_size.py` is a directory size analysis tool that displays directory structure in tree format and sorts by size.

**Features**:
- 📊 **Tree-style Display** - Shows directories and files in a tree structure
- 📈 **Smart Sorting** - Sorts by size from smallest to largest for easy identification
- 🔍 **Auto Check** - Automatically checks video file status in leaf directories (bottom-level directories)
- 📝 **Issue Report** - Automatically generates check reports listing problematic directories

**Usage**:
```bash
# Basic usage (automatically checks and generates report)
python3 tools/dir_tree_size.py "/path/to/directory"

# Skip checking, only show directory structure
python3 tools/dir_tree_size.py "/path/to/directory" --no-check
```

**Check Features**:
- ✅ **Missing mp4 Files** - Detects if leaf directories are missing `.mp4` files
- ✅ **m4s Files Present** - Detects if `.m4s` files exist in leaf directories (usually incomplete downloads or fragmented files)

**Report Generation**:
- Check reports are automatically generated in the checked directory
- Filename format: `directory_name_检查报告_timestamp.log`
- Report includes: List of problematic directories, specific issue types, statistics

**Example Output**:
```
/Volumes/Data-12T-mybook/多媒体资料/视频/Bilibili/ (1.23 TB)
├── 番剧-33415-名侦探柯南（中配） (50.2 GB)
│   ├── BV1xx411c7mD-第1集 (500 MB)
│   └── BV1xx411c7mE-第2集 (480 MB)
└── 收藏夹-123456-我的收藏 (30.5 GB)

Report generated: /path/to/xxx_检查报告_20250116_123456.log
Found 5 leaf directories with issues
```

## 🎯 Perfect For

- **Content Creators** - Continuously track and backup latest uploads from followed UP masters
- **Educators** - Automatically sync course updates and educational resources
- **Media Collectors** - Intelligently manage updates from favorites and watchlists
- **Researchers** - Automate collection and organization of research-related video materials

## 🛠️ Tech Stack

Built with Python 3.8+, Flask, yutto, and modern web technologies for reliability and performance.

## 🤝 Contributing

We welcome contributions! Submit Issues or Pull Requests to help improve BiliSyncer.

## 📜 License

MIT Licensed - see [LICENSE](LICENSE) for details.

---

⭐ **Star this project if it helps you manage your Bilibili content!** 