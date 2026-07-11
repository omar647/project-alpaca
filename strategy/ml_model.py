"""Train an ML model on PCA components and turn probabilities into a signal.

Target  : binary — next-day return > 0  (1 = up, 0 = down/flat)
Signal  : Long (1) if P(up) > threshold (default 0.60), else Flat (0)

The PCA is fit on the training window only, so the test-period backtest is
free of look-ahead leakage. The whole thing is packaged into a ``SignalModel``
that can also score the single most recent bar for live paper trading.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
from sklearn.ensemble import GradientBoostingClassifier, RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.neural_network import MLPClassifier
from sklearn.svm import SVC

from .features import FEATURE_COLUMNS, build_features
from .pca import PCAModel, fit_pca

PROB_THRESHOLD = 0.60
DEFAULT_MODEL = "gradient_boosting"


def _make_estimator(name: str):
    name = name.lower()
    if name in ("rf", "random_forest", "randomforest"):
        return RandomForestClassifier(
            n_estimators=300, max_depth=5, min_samples_leaf=20,
            random_state=42, n_jobs=-1,
        )
    if name in ("logreg", "logistic", "logistic_regression"):
        return LogisticRegression(max_iter=1000, C=1.0)
    if name in ("gb", "gradient_boosting", "gbm"):
        return GradientBoostingClassifier(random_state=42)
    if name in ("svm", "svc"):
        return SVC(probability=True, random_state=42)
    if name in ("mlp", "neural_net"):
        return MLPClassifier(hidden_layer_sizes=(32, 16), max_iter=1000, random_state=42)
    raise ValueError(f"Unknown model {name!r}.")


@dataclass
class SignalModel:
    name: str
    estimator: object
    pca: PCAModel
    threshold: float
    feat: pd.DataFrame          # full engineered feature frame (incl. OHLCV)
    test_index: pd.DatetimeIndex
    proba: pd.Series            # P(up) over the *test* window
    signal: pd.Series           # 0/1 long-flat signal over the test window
    target: pd.Series           # realised next-day up/down over the test window

    # ---- convenience views -------------------------------------------------
    def test_frame(self) -> pd.DataFrame:
        """OHLCV rows for the test window (aligned to the signal)."""
        return self.feat.loc[self.test_index]

    def latest_signal(self) -> dict:
        """Score the single most recent bar for live paper trading.

        Returns a dict with the probability, the 0/1 signal, and a label.
        """
        last = self.feat.iloc[[-1]]
        pcs = self.pca.transform(last[FEATURE_COLUMNS])
        prob = float(self.estimator.predict_proba(pcs.values)[0, 1])
        sig = int(prob > self.threshold)
        return {
            "date": last.index[-1],
            "close": float(last["close"].iloc[-1]),
            "probability": prob,
            "signal": sig,
            "label": "LONG" if sig else "FLAT",
        }


def train_signal_model(
    df: pd.DataFrame,
    model: str = DEFAULT_MODEL,
    threshold: float = PROB_THRESHOLD,
    test_size: float = 0.30,
) -> SignalModel:
    """Build features, fit PCA + model on the training split, score the test split."""
    feat = build_features(df)

    # Target: next-day return > 0.
    fwd_ret = feat["close"].shift(-1) / feat["close"] - 1.0
    target = (fwd_ret > 0).astype(int)

    # Drop the final row (no next-day return known yet) for supervised fitting.
    usable = feat.index[:-1]
    X_all = feat.loc[usable, FEATURE_COLUMNS]
    y_all = target.loc[usable]

    # Chronological split (no shuffling — this is a time series).
    split = int(len(X_all) * (1 - test_size))
    X_train, X_test = X_all.iloc[:split], X_all.iloc[split:]
    y_train, y_test = y_all.iloc[:split], y_all.iloc[split:]

    # PCA fit on training features only.
    pca = fit_pca(X_train)
    Z_train = pca.transform(X_train)
    Z_test = pca.transform(X_test)

    est = _make_estimator(model)
    est.fit(Z_train.values, y_train.values)

    proba = pd.Series(est.predict_proba(Z_test.values)[:, 1], index=X_test.index, name="proba")
    signal = (proba > threshold).astype(int).rename("signal")

    return SignalModel(
        name=model, estimator=est, pca=pca, threshold=threshold,
        feat=feat, test_index=X_test.index,
        proba=proba, signal=signal, target=y_test.rename("target"),
    )
