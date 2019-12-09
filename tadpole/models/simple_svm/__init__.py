import pandas as pd
import numpy as np
from sklearn import svm
from sklearn.preprocessing import StandardScaler
from sklearn.pipeline import Pipeline

import logging
logger = logging.getLogger(__name__)


class SimpleSVM:
    def __init__(self):
        self.diagnosis_model = Pipeline([
            ('scaler', StandardScaler()),
            ('classifier', svm.SVC(kernel="linear", probability=True)),
        ])
        self.adas_model = Pipeline([
            ('scaler', StandardScaler()),
            ('classifier', svm.SVR(kernel="linear")),
        ])
        self.ventricles_model = Pipeline([
            ('scaler', StandardScaler()),
            ('classifier', svm.SVR(kernel="linear")),
        ])

    def train_model(self, model, train_df, X_train, var_name):
        # remove rows with NaN future values
        Y_train_var = train_df[var_name]
        not_nans = np.logical_not(np.isnan(Y_train_var))
        X_train_var = X_train[not_nans]
        Y_train_var = Y_train_var[not_nans]
        model.fit(X_train_var, Y_train_var)

    def preprocess(self, train_df):
        logger.info("Pre-processing")
        train_df = train_df.copy()
        if 'Diagnosis' not in train_df.columns:
            train_df = train_df.replace({'DXCHANGE': {4: 2, 5: 3, 6: 3, 7: 1, 8: 2, 9: 1}})
            train_df = train_df.rename(columns={"DXCHANGE": "Diagnosis"})

        # Sort the dataframe based on age for each subject
        train_df = train_df.sort_values(by=['RID', 'Years_bl'])

        if 'Ventricles_ICV' not in train_df.columns:
            train_df["Ventricles_ICV"] = train_df["Ventricles"].values / train_df["ICV_bl"].values

        # Select features
        train_df = train_df[
            ["RID", "Diagnosis", "ADAS13", "Ventricles_ICV", "Ventricles", "ICV_bl"]
        ]

        # Force values to numeric
        train_df = train_df.astype("float64", errors='ignore')

        return train_df

    def set_futures(self, train_df):
        # Get future value from each row's next row, e.g. shift the column one up
        for predictor in ["Diagnosis", "ADAS13", 'Ventricles_ICV']:
            train_df["Future_" + predictor] = train_df[predictor].shift(-1)

        # Drop each last row per patient
        train_df = train_df.drop(train_df.groupby('RID').tail(1).index.values)
        return train_df

    def train(self, train_set_path):
        train_df = pd.read_csv(train_set_path)
        train_df = self.preprocess(train_df)
        train_df = self.set_futures(train_df)

        # Select columns for training
        X_train = train_df[["Diagnosis", "ADAS13", "Ventricles_ICV"]]

        # fill NaNs with mean
        X_train = X_train.fillna(X_train.mean())

        logger.info("Training models")
        self.train_model(self.diagnosis_model, train_df, X_train, "Future_Diagnosis")
        self.train_model(self.adas_model, train_df, X_train, "Future_ADAS13")
        self.train_model(self.ventricles_model, train_df, X_train, "Future_Ventricles_ICV")

    def predict(self, test_series, predict_datetime):
        logger.info("Predicting")
        # Do a single prediction for a single patient.

        test_df = test_series.to_frame().T

        predict_df_preprocessed = self.preprocess(test_df)

        # get the final row (last known value that is not NaN for each variable)
        final_row = [
            predict_df_preprocessed['Diagnosis'].dropna().iloc[-1],
            predict_df_preprocessed['ADAS13'].dropna().iloc[-1],
            predict_df_preprocessed['Ventricles_ICV'].dropna().iloc[-1]
        ]

        diag_probas = self.diagnosis_model.predict_proba([final_row])[0]

        return {
            'CN relative probability': diag_probas[0],
            'MCI relative probability': diag_probas[1],
            'AD relative probability': diag_probas[2],

            'ADAS13': self.adas_model.predict([final_row])[0],
            'ADAS13 50% CI lower': 0,
            'ADAS13 50% CI upper': 0,

            'Ventricles_ICV': self.ventricles_model.predict([final_row])[0],
            'Ventricles_ICV 50% CI lower': 0,
            'Ventricles_ICV 50% CI upper': 0,
        }