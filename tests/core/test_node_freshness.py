import json
import time

import backend.intelligence_pipeline as pipeline


def write_node(directory, name, timestamp, cpu=50):
    path = directory / f"{name}.json"
    path.write_text(json.dumps({
        "node": name,
        "node_name": name,
        "timestamp": timestamp,
        "metrics": {
            "cpu": cpu,
            "memory": 40,
            "disk": 50,
            "processes": [],
        },
    }))


def test_load_nodes_accepts_fresh_node(tmp_path, monkeypatch):
    now = time.time()
    write_node(tmp_path, "fresh", now - 10)

    monkeypatch.setattr(pipeline, "NODES_DIR", str(tmp_path))

    nodes = pipeline.load_nodes()

    assert len(nodes) == 1
    assert nodes[0]["node"] == "fresh"


def test_load_nodes_rejects_stale_node(tmp_path, monkeypatch):
    now = time.time()
    write_node(tmp_path, "stale", now - 121, cpu=95)

    monkeypatch.setattr(pipeline, "NODES_DIR", str(tmp_path))

    nodes = pipeline.load_nodes()

    assert nodes == []


def test_load_nodes_rejects_future_node(tmp_path, monkeypatch):
    now = time.time()
    write_node(tmp_path, "future", now + 31)

    monkeypatch.setattr(pipeline, "NODES_DIR", str(tmp_path))

    nodes = pipeline.load_nodes()

    assert nodes == []


def test_load_nodes_rejects_invalid_timestamp(tmp_path, monkeypatch):
    write_node(tmp_path, "invalid", "not-a-timestamp")

    monkeypatch.setattr(pipeline, "NODES_DIR", str(tmp_path))

    nodes = pipeline.load_nodes()

    assert nodes == []


def test_load_nodes_keeps_fresh_and_excludes_stale(tmp_path, monkeypatch):
    now = time.time()

    write_node(tmp_path, "fresh", now - 20, cpu=30)
    write_node(tmp_path, "stale", now - 300, cpu=99)

    monkeypatch.setattr(pipeline, "NODES_DIR", str(tmp_path))

    nodes = pipeline.load_nodes()

    assert [node["node"] for node in nodes] == ["fresh"]
