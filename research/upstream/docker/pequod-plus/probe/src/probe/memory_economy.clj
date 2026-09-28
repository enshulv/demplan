(ns probe.memory-economy
  "Builders for the in-memory data shapes that `pequod-plus.util/update-surpluses-prices` reads:
  worker councils, consumer councils, the price table and the category multipliers."
  (:require [probe.report :as report]))

(defn worker-council
  "A worker council in the shape `compute-surpluses-prices` reads. `inputs` maps a category key
  (`:intermediate-inputs`, `:nature`, `:labor`) to [[commodity-id quantity] ...]."
  [industry product output inputs]
  (let [shape (fn [category quantities-key]
                (let [pairs (get inputs category [])]
                  {category (mapv (fn [[id _]] {:coefficient id :exponent 0.1}) pairs)
                   quantities-key (mapv (comp double second) pairs)}))]
    (merge {:industry industry :product product :output (double output)
            :pollutants [] :pollutant-quantities []}
           (shape :intermediate-inputs :intermediate-input-quantities)
           (shape :nature :nature-quantities)
           (shape :labor :labor-quantities))))

(defn consumer-council
  "A consumer council whose demand for private (public) good i is element i-1 of `private` (`public`)."
  [private public]
  {:private-goods (vec (map-indexed (fn [i d] {:id (inc i) :demand (double d)}) private))
   :public-goods (vec (map-indexed (fn [i d] {:id (inc i) :demand (double d)}) public))
   :pollutant-permissions []})

(defn initial-price-data
  "The price table from the program's own `initialize-prices`, with `n` commodities per category
  and every price at 700."
  [n]
  (let [initialize-prices (report/resolve-fn 'pequod-plus.util/initialize-prices)]
    (:price-data (initialize-prices {:init-private-good-price 700.0 :init-intermediate-price 700.0
                                     :init-labor-price 700.0 :init-nature-price 700.0
                                     :init-public-good-price 700.0 :init-pollutant-price 700.0
                                     :private-goods n :intermediate-inputs n :resources n
                                     :labors n :public-goods n :pollutants 1}))))

(def initial-price-delta-data
  "The category multipliers the program starts from (`csvgen/price-delta-data`)."
  {:private-goods 0.05 :intermediate-inputs 0.05 :nature 0.05 :labor 0.05
   :public-goods 0.05 :pollutants 0.05})

(def categories
  "The five categories the program prices when pollutants are off."
  [:private-goods :intermediate-inputs :nature :labor :public-goods])
