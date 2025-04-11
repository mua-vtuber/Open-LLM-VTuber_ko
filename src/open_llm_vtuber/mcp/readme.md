## MCP for Open-LLM-VTuber

#### 📄 Introduction

> MCP (Model Context Protocol) is an open protocol that standardizes how applications provide context to LLMs. Think of MCP like a USB-C port for AI applications. Just as USB-C provides a standardized way to connect your devices to various peripherals and accessories, MCP provides a standardized way to connect AI models to different data sources and tools.
> From: [MCP Official Document](https://modelcontextprotocol.io/introduction)

As MCP is a powerful tool for LLMs to call functions, reach resources on your computer and give some useful prompts, implementing it in Open-LLM-VTuber seems a high rewarding action. So it just right here.


#### 📁 File Structure

- `mcp/` - The main folder of MCP module.
    - `servers/` - Custom MCP servers should be stored here (or may change it at 'mcp_servers.json').
        - `example.py` - Basic python MCP server example, contains a tool named `calculate_bmi`.
    - `client.py` - The MCP client implemention.
    - `mcp_servers.json` - Config file for MCP.
    - `readme.md` - You are reading it.
    - `readme.zh.md` - The Chinese version of readme file.
    - `server_manager.py` - The MCP servers manager.


#### 🔧 Usage

Well, you don't have to modify client file, because about when and how to interact with a MCP server is already defined. If you're a project(Open-LLM-VTuber) developer, you can refer to [`Developing`](#️-developing). 

So for common users (or MCP server developers), you can follow these steps to add your MCP server:

1. Confirm your **MCP server type**. Here we categorize servers into two types:
    - ***official***: refer to the servers you found at [Model Context Protocol servers](https://github.com/modelcontextprotocol/servers) or any server can be run via `npx` or `uvx` (see details at [References#uvx & npx](#uvx--npx)).
    - ***custom***: refer to the servers developed by yourself or servers cannot be run via `npx` or `uvx`, but they should be run via `python` or `node`.
2. Confirm your **MCP server file type** is supported. Currently, we support `.py`(Python files) and `.js`(Compiled from TypeScipt).
3. Open `mcp_servers.json`
4. For ***official*** MCP servers, follow these steps:


#### 📚 References

##### uvx & npx
Requirements for Running servers via `uvx` or `npx`

**uvx:**

- **Installed the python package and project manager - uv**, see [uv Document](https://docs.astral.sh/uv/getting-started/installation/) for further information.
- The tool must be published and registered on **PyPI** (Python Package Index)
- It automatically downloads and installs the tool from PyPI when running (if not locally available)
- Suitable for simply running Python CLI tools without explicit installation

For example: `uvx black .` will automatically download and run the black code formatting tool

**npx:**

- **Installed Node.js**, see [Node.js Website](https://nodejs.org/en)
- Can run locally installed npm packages (project dependencies or global packages)
- Can directly fetch and run uninstalled packages from the npm registry
- The package must be registered in the npm repository
- The package to be executed needs to define executable commands in its package.json

For example: `npx create-react-app my-app` will download and run the create-react-app tool to create a project


#### 🛠️ Developing

Test context hyper link