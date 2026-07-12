"""Standardize features and reduce them with PCA.

Keeps the smallest number of principal components that together explain at
least ``VARIANCE_TARGET`` (80%) of the variance, then uses those components as
the ML model's inputs.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
from sklearn.decomposition import PCA
from sklearn.preprocessing import StandardScaler

VARIANCE_TARGET = 0.80


@dataclass
class PCAModel:
    scaler: StandardScaler
    pca: PCA
    n_components: int
    columns: list[str]

    def transform(self, X: pd.DataFrame) -> pd.DataFrame:
        """Apply the fitted scaler + PCA to new feature rows."""
        Xs = self.scaler.transform(X[self.columns].values)
        comps = self.pca.transform(Xs)[:, : self.n_components]
        cols = [f"PC{i + 1}" for i in range(self.n_components)]
        return pd.DataFrame(comps, index=X.index, columns=cols)

    @property
    def explained_variance_ratio(self) -> np.ndarray:
        return self.pca.explained_variance_ratio_


def fit_pca(X: pd.DataFrame, variance_target: float = VARIANCE_TARGET) -> PCAModel:
    """Fit StandardScaler + PCA on ``X`` and pick components for >=80% variance.

    Only fit on the data you pass in (i.e. the training window) to avoid
    look-ahead leakage into the test period.
    """
    columns = list(X.columns)
    scaler = StandardScaler().fit(X.values)
    Xs = scaler.transform(X.values)

    pca = PCA().fit(Xs)
    cum = np.cumsum(pca.explained_variance_ratio_)
    n_components = int(np.searchsorted(cum, variance_target) + 1)
    n_components = max(1, min(n_components, pca.n_components_))

    return PCAModel(scaler=scaler, pca=pca, n_components=n_components, columns=columns)
