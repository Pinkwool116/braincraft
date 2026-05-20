"""
知识图谱可视化服务端
读取 memory_graph 中的 JSON 数据，通过 /api/graph 接口提供给前端。
仅使用 Python 标准库，零额外依赖。
"""
import http.server
import json
import os
import socket as socket_module
import subprocess
import sys
from pathlib import Path
from collections import Counter

PORT = 8081
DATA_DIR = r"F:\pinkwool\project\MindCraft\braincraft\bots\BrainyBot\memory_graph"


class GraphAPIHandler(http.server.SimpleHTTPRequestHandler):
    graph_dir = None  # 由外部设置

    def __init__(self, *args, **kwargs):
        viz_dir = Path(__file__).resolve().parent
        super().__init__(*args, directory=str(viz_dir), **kwargs)

    def do_GET(self):
        if self.path == "/api/graph":
            self._handle_graph_api()
        else:
            super().do_GET()

    def _handle_graph_api(self):
        try:
            data = self._load_graph_data()
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self.wfile.write(json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8"))
        except Exception as e:
            self.send_response(500)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.end_headers()
            self.wfile.write(json.dumps({"error": str(e)}, ensure_ascii=False).encode("utf-8"))

    def _load_graph_data(self):
        graph_dir = Path(GraphAPIHandler.graph_dir) if GraphAPIHandler.graph_dir else None
        if not graph_dir or not graph_dir.exists():
            raise FileNotFoundError(f"数据目录不存在: {graph_dir}")

        nodes_dir = graph_dir / "nodes"
        edges_file = graph_dir / "edges" / "relationships.json"

        nodes = []
        if nodes_dir.exists():
            for filename in sorted(os.listdir(nodes_dir)):
                if not filename.endswith(".json"):
                    continue
                filepath = nodes_dir / filename
                try:
                    with open(filepath, "r", encoding="utf-8") as f:
                        node_list = json.load(f)
                        for node_data in node_list:
                            node_data["invalid"] = node_data.get("invalid_at") is not None
                            nodes.append(node_data)
                except Exception as e:
                    print(f"[WARN] 加载节点文件失败 {filepath}: {e}", file=sys.stderr)

        edges = []
        if edges_file.exists():
            try:
                with open(edges_file, "r", encoding="utf-8") as f:
                    edge_list = json.load(f)
                    for edge_data in edge_list:
                        edge_data["invalid"] = edge_data.get("invalid_at") is not None
                        edges.append(edge_data)
            except Exception as e:
                print(f"[WARN] 加载边文件失败 {edges_file}: {e}", file=sys.stderr)

        active_nodes = [n for n in nodes if not n["invalid"]]
        active_edges = [e for e in edges if not e["invalid"]]

        nodes_by_type = Counter(n["type"] for n in active_nodes)
        edges_by_relation = Counter(e["relation"] for e in active_edges)
        most_accessed = sorted(active_nodes, key=lambda n: n.get("access_count", 0), reverse=True)[:10]
        all_relations = sorted(set(e["relation"] for e in edges))

        stats = {
            "total_nodes": len(active_nodes),
            "total_nodes_with_invalid": len(nodes),
            "total_edges": len(active_edges),
            "total_edges_with_invalid": len(edges),
            "invalid_nodes": len(nodes) - len(active_nodes),
            "invalid_edges": len(edges) - len(active_edges),
            "nodes_by_type": dict(nodes_by_type),
            "edges_by_relation": dict(edges_by_relation),
            "all_relations": all_relations,
            "most_accessed": [
                {"id": n["id"], "content": n["content"], "type": n["type"], "access_count": n.get("access_count", 0)}
                for n in most_accessed
            ],
        }

        return {"nodes": nodes, "edges": edges, "stats": stats}

    def log_message(self, format, *args):
        if "/api/graph" in str(args):
            print(f"[{self.address_string()}] {args[0]}")


def kill_existing():
    """杀掉占用同一端口的旧进程，确保干净启动。"""
    try:
        result = subprocess.run(
            ["netstat", "-ano"],
            capture_output=True, text=True, timeout=5
        )
        pids = set()
        for line in result.stdout.splitlines():
            if f":{PORT}" in line and "LISTENING" in line:
                parts = line.strip().split()
                pids.add(parts[-1])
        for pid in pids:
            print(f"[INFO] 杀掉占用端口 {PORT} 的旧进程 PID={pid}")
            subprocess.run(["taskkill", "/F", "/PID", pid], capture_output=True)
    except Exception:
        pass  # netstat/taskkill 不可用时静默跳过


def main():
    data_dir = Path(DATA_DIR)
    if not data_dir.exists():
        print(f"错误: 数据目录不存在: {data_dir}")
        print(f"请修改 server.py 顶部的 DATA_DIR 配置")
        sys.exit(1)

    GraphAPIHandler.graph_dir = str(data_dir)

    kill_existing()

    print(f"知识图谱可视化服务端")
    print(f"数据目录: {data_dir}")
    print(f"服务地址: http://localhost:{PORT}")
    print(f"按 Ctrl+C 停止服务，或直接关闭此窗口")
    print()

    server = http.server.HTTPServer(("0.0.0.0", PORT), GraphAPIHandler)
    server.timeout = 0.5  # 每 0.5s 超时一次，让 Ctrl+C 能即时响应
    print("服务已启动（按 Ctrl+C 停止）")
    try:
        while True:
            try:
                server.handle_request()
            except socket_module.timeout:
                pass  # 无请求时继续循环，检查 KeyboardInterrupt
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
        print("服务已停止")


if __name__ == "__main__":
    main()
