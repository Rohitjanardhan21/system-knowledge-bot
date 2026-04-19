# ---------------------------------------------------------
# 🧠 TRAIN ANOMALY MODEL (HYBRID AI PIPELINE)
# ---------------------------------------------------------

import json
import os
import argparse
import numpy as np

from backend.core.anomaly_model import AnomalyModel


# ---------------------------------------------------------
# 📂 LOAD DATASET
# ---------------------------------------------------------
def load_dataset(path):
    if not os.path.exists(path):
        raise FileNotFoundError(f"Dataset not found: {path}")

    with open(path, "r") as f:
        data = json.load(f)

    if not isinstance(data, list):
        raise ValueError("Dataset must be a list of frames")

    return data


# ---------------------------------------------------------
# 🧹 EXTRACT FEATURES
# ---------------------------------------------------------
def extract_features(dataset):
    features_list = []

    for i, frame in enumerate(dataset):
        try:
            features = frame["perception"]["features"]

            if not isinstance(features, dict):
                continue

            features_list.append(features)

        except KeyError:
            continue

    if len(features_list) == 0:
        raise ValueError("No valid feature data found in dataset")

    return features_list


# ---------------------------------------------------------
# 📊 BASIC DATA STATS
# ---------------------------------------------------------
def print_dataset_stats(features_list):
    print("\n📊 DATASET STATS")
    print(f"Total samples: {len(features_list)}")

    keys = set().union(*features_list)
    print(f"Feature keys: {list(keys)}")

    sample = features_list[0]
    print(f"Sample feature vector: {sample}")


# ---------------------------------------------------------
# 🧠 TRAIN MODEL
# ---------------------------------------------------------
def train_model(features_list, model_path):

    model = AnomalyModel(model_path=model_path)

    print("\n⚙️ Feeding data into model...")

    for features in features_list:
        model.update(features)

    print("🧠 Training model...")
    success = model.train()

    if not success:
        raise RuntimeError("Training failed (insufficient data?)")

    print("✅ Model trained successfully")
    print(f"📦 Saved at: {model_path}")

    return model


# ---------------------------------------------------------
# 📈 QUICK EVALUATION
# ---------------------------------------------------------
def evaluate_model(model, features_list):

    print("\n📈 EVALUATING MODEL...")

    scores = []

    for features in features_list[:50]:  # sample evaluation
        result = model.score(features)
        scores.append(result["score"])

    if scores:
        print(f"Average anomaly score: {round(np.mean(scores), 3)}")
        print(f"Max anomaly score: {round(np.max(scores), 3)}")
        print(f"Min anomaly score: {round(np.min(scores), 3)}")


# ---------------------------------------------------------
# 🚀 MAIN
# ---------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(description="Train Anomaly Model")

    parser.add_argument(
        "--dataset",
        type=str,
        default="dataset.json",
        help="Path to dataset JSON"
    )

    parser.add_argument(
        "--output",
        type=str,
        default="models/anomaly.pkl",
        help="Output model path"
    )

    args = parser.parse_args()

    print("\n🚀 STARTING TRAINING PIPELINE")

    # -----------------------------
    # LOAD DATA
    # -----------------------------
    dataset = load_dataset(args.dataset)

    # -----------------------------
    # EXTRACT FEATURES
    # -----------------------------
    features_list = extract_features(dataset)

    # -----------------------------
    # STATS
    # -----------------------------
    print_dataset_stats(features_list)

    # -----------------------------
    # TRAIN
    # -----------------------------
    model = train_model(features_list, args.output)

    # -----------------------------
    # EVALUATE
    # -----------------------------
    evaluate_model(model, features_list)

    print("\n🎯 TRAINING COMPLETE")


# ---------------------------------------------------------
if __name__ == "__main__":
    main()
