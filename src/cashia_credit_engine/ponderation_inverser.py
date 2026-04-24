import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from scipy.optimize import curve_fit

from cashia_core.ponderation.pm_amount_finder import *
from cashia_core.common_tools.configuration.cashiaconstants import *


# Función logarítmica
def modelo_logaritmico(x, a, b):
    return a * np.log(x) + b


class PonderationInverser:
    def __init__(
        self, threshold, base_amount, max_amount, num_intervals=100, method=CONSERVATIVE
    ):

        self.threshhold = threshold
        self.base_amount = base_amount
        self.max_amount = max_amount
        self.num_intervals = num_intervals
        self.method = method

        # Creamos una lista con las probabilidades menosres que el threshold que es cuando aplicamos ponderación
        probabilities = np.linspace(0, threshold, num_intervals)
        data = {"Proba": probabilities}
        df = pd.DataFrame(data)

        # Creamos los valores de la ponderación (valor exponencial de la función)
        exponentials = np.arange(0.1, 15, 0.2)

        # Recorremos cada uno de los valode de ponderación
        for e in exponentials:
            colname = e
            weighter = AmountWeighting(threshold, method, e)

            # Agregamos la columna de la ponderación usada. Al monto base le agregamos un monto complementario
            # que va de 0 a (max_amount-base_amount) en función de la probabilidad.
            df[colname] = df.apply(
                lambda row: base_amount
                + weighter.complementary_amount(max_amount - base_amount, row["Proba"]),
                axis=1,
            )

        my_stats = df.drop(columns={"Proba"}).describe()

        means = my_stats.loc[["mean"]].T

        # Ajustar el modelo a los datos
        parametros, __ = curve_fit(
            modelo_logaritmico, means.index.values, means["mean"].values
        )

        # Parámetros ajustados
        self.a, self.b = parametros

        self.max_ponderation = self.ponderation_from_mean_amount(base_amount)

    def ponderation_from_mean_amount(self, mean_amount):

        ponderation = np.exp((mean_amount - self.b) / self.a)

        return ponderation

    def mean_amount_from_ponderation(self, ponderation):

        return modelo_logaritmico(ponderation, self.a, self.b)


def get_epsilons(goal_amount, average_amounts, n):

    num_credits = sum(n)
    w = []
    for n_i in n:
        w_i = n_i / num_credits
        w.append(w_i)

    amount_avg = np.average(average_amounts, weights=w)

    # print(f"\nSearched amount:{goal_amount} current amount: {amount_avg}")

    w_max = max(w)

    w2 = sum(weight**2 for weight in w)

    e_max = (goal_amount - amount_avg) * w_max / w2

    epsilons = []

    for i in range(0, 4):
        e = e_max * w[i] / w_max
        epsilons.append(e)

    new_amounts = np.array(average_amounts) + np.array(epsilons)

    # print(f"\nepsilons: {epsilons}")
    # print(f"\nNew amounts: {new_amounts}")

    new_amount_avg = np.average(new_amounts, weights=w)
    # print(f"\nNew average: {new_amount_avg}")

    return epsilons


# Programa de prueba
if __name__ == "__main__":
    threshold = 0.40
    base_amount = 3_000
    max_amount = 17_000
    num_intervals = 100

    ponderator_1 = PonderationInverser(
        threshold, base_amount, max_amount, num_intervals, CONSERVATIVE
    )
    exponentials_1 = np.arange(0.1, ponderator_1.max_ponderation, 0.2)
    mean_values_1 = ponderator_1.mean_amount_from_ponderation(exponentials_1)

    ponderator_2 = PonderationInverser(
        threshold, base_amount, max_amount - 2000, num_intervals, CONSERVATIVE
    )
    exponentials_2 = np.arange(0.1, ponderator_2.max_ponderation, 0.2)
    mean_values_2 = ponderator_2.mean_amount_from_ponderation(exponentials_2)

    ponderator_3 = PonderationInverser(
        threshold, 7000, max_amount, num_intervals, CONSERVATIVE
    )
    exponentials_3 = np.arange(0.1, ponderator_3.max_ponderation, 0.2)
    mean_values_3 = ponderator_3.mean_amount_from_ponderation(exponentials_3)

    print(
        f"ponderación máxima modelo {1} : {ponderator_1.max_ponderation} base amount: {ponderator_1.base_amount} ponderation: {ponderator_1.ponderation_from_mean_amount(ponderator_1.base_amount)}"
    )
    print(
        f"ponderación máxima modelo {2} : {ponderator_2.max_ponderation} base amount: {ponderator_2.base_amount} ponderation: {ponderator_2.ponderation_from_mean_amount(ponderator_2.base_amount)}"
    )
    print(
        f"ponderación máxima modelo {3} : {ponderator_3.max_ponderation} base amount: {ponderator_3.base_amount} ponderation: {ponderator_3.ponderation_from_mean_amount(ponderator_3.base_amount)}"
    )

    plt.plot(
        exponentials_1,
        mean_values_1,
        label=f"Ajuste logarítmico {max_amount}",
        color="blue",
    )
    plt.plot(
        exponentials_2,
        mean_values_2,
        label=f"Ajuste logarítmico {max_amount-2000}",
        color="red",
    )
    plt.plot(
        exponentials_3, mean_values_3, label=f"Ajuste logarítmico {0}", color="green"
    )

    plt.xlabel("ponderation")
    plt.ylabel("mean amount")
    plt.legend()
    plt.title("Modelos de ponderación")
    plt.show()

    amounts = [9000, 9000, 9300, 9100]
    n = [10, 7, 15, 20]

    epsilons = get_epsilons(7500, amounts, n)

    print(epsilons)
