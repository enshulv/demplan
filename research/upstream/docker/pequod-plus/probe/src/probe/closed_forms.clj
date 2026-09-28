(ns probe.closed-forms
  "Worker-council proposals computed by the program's closed-form solutions.

  Reads the cases written by `make_closed_form_cases.py` (an EDN file), passes each worker council to
  the function the program calls once per council and round, and writes the returned output,
  effort and input quantities to a tab-separated file for `verify_closed_forms.py`.

  The per-council function depends on the commit:
  - `pequod-plus.csvgen/process-wc` (called by `proposal-db`), which picks `solution-N` by the
    number of inputs N;
  - `pequod-plus.util/proposal`, where `pequod-plus.csvgen` does not load.
  Both are given the council's parameters and the prices of its inputs and of its product."
  (:require [clojure.edn :as edn]
            [clojure.java.io :as io]
            [clojure.string :as str]
            [probe.report :as report]))

(def input-categories
  "Input categories in the order the program concatenates exponents and prices."
  [:intermediate-inputs :nature :labor])

(defn- product-category
  "Price category of a worker council's product, by its `:industry` code."
  [industry]
  (case (long industry) 0 :private-goods 1 :intermediate-inputs 2 :public-goods))

(defn- case-prices
  "Price maps (category -> id -> price) of a case: its named price set with its overrides on top."
  [price-sets {:keys [price-set price-overrides]}]
  (merge-with merge (get price-sets (keyword price-set)) price-overrides))

(defn- via-process-wc
  "Calls `csvgen/process-wc` with the council as the database rows `proposal-db` would pass."
  [process-wc prices {:keys [industry product a s c k inputs]}]
  (let [wc-id 1
        rows (fn [category] {wc-id (mapv (fn [[id b]] {:coefficient id :exponent b}) (get inputs category))})
        wc {:id wc-id :industry industry :product product :total_factor_productivity a
            :disutility_of_effort_coefficient s :effort_elasticity c :disutility_of_effort_exponent k}
        result (process-wc false (rows :intermediate-inputs) (rows :nature) (rows :labor) {}
                           (:intermediate-inputs prices) (:labor prices) (:nature prices) {}
                           (:private-goods prices) (:public-goods prices) wc)]
    (when (map? result)
      {:output (:output result) :effort (:effort result)
       :x (vec (mapcat #(get result %) input-categories))})))

(defn- via-proposal
  "Calls `util/proposal` with the council in the in-memory shape it reads."
  [proposal prices {:keys [industry product a s c k inputs]}]
  (let [price-list (fn [category] (mapv (fn [[id p]] {:id id :price p}) (sort (get prices category))))
        wc (merge {:industry industry :product product :total-factor-productivity a
                   :effort-elasticity c :disutility-of-effort {:coefficient s :exponent k}}
                  (into {} (for [category input-categories]
                             [category (mapv (fn [[id b]] {:coefficient id :exponent b}) (get inputs category))])))
        result (proposal false (into {} (for [category (conj input-categories :private-goods :public-goods)]
                                          [category (price-list category)]))
                         wc)]
    (when (map? result)
      {:output (:output result) :effort (:effort result)
       :x (vec (mapcat #(get result %) [:intermediate-input-quantities :nature-quantities :labor-quantities]))})))

(defn- entry-point
  "The per-council function available at this commit, as [label f]."
  []
  (if-let [process-wc (report/resolve-fn 'pequod-plus.csvgen/process-wc)]
    ["csvgen/process-wc" (partial via-process-wc process-wc)]
    (when-let [proposal (report/resolve-fn 'pequod-plus.util/proposal)]
      ["util/proposal" (partial via-proposal proposal)])))

(defn -main
  "Usage: lein run -m probe.closed-forms CASES.edn OUT.tsv"
  [cases-path out-path & _]
  (let [{:keys [price-sets cases]} (edn/read-string (slurp cases-path))
        [label solve] (entry-point)]
    (println (str "closed-forms: " (count cases) " cases through " label))
    (with-open [w (io/writer out-path)]
      (.write w "case_id\tentry_point\tn_inputs\toutput\teffort\tx\n")
      (doseq [c cases]
        (let [n (reduce + (map #(count (get-in c [:inputs %])) input-categories))
              result (solve (case-prices price-sets c) c)]
          (.write w (str/join "\t" [(:id c) label n
                                    (report/num-str (:output result)) (report/num-str (:effort result))
                                    (str/join ";" (map report/num-str (:x result)))]))
          (.write w "\n"))))
    (println (str "closed-forms: wrote " out-path))
    (shutdown-agents)))
