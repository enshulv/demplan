(ns probe.demand-by-commodity
  "Whether pequod-plus separates consumer demand for private and public goods by commodity.

  Part 1 calls `pequod-plus.util/update-surpluses-prices`, the per-round step of the in-memory
  loop, on an economy with two commodities per category and two consumer councils.
  Part 2 runs one round of `pequod-plus.csvgen/iterate-plan-improved`, the per-round step that
  `pequod-plus.csvgen/-main` runs, on the SQLite economy of `probe.sqlite-economy`.

  Every table prints, per commodity, the value the program computed next to the value obtained
  here by adding up the same inputs commodity by commodity. For consumer demand it also prints
  the sum over the whole category. Supply and the demand for inputs, which the program selects
  by commodity id, are the control: they should match the per-commodity sums."
  (:require [probe.memory-economy :as economy]
            [probe.report :as report]))

;; ---------------------------------------------------------------------------------------------
;; Part 1: in-memory step

(def worker-councils
  "Six worker councils, one per (industry, product). Input quantities are [commodity-id quantity]."
  [(economy/worker-council 0 1 25 {:intermediate-inputs [[1 3]] :nature [[1 5]] :labor [[1 4]]})
   (economy/worker-council 0 2 75 {:intermediate-inputs [[2 6]] :nature [[2 2]] :labor [[1 1] [2 7]]})
   (economy/worker-council 1 1 12 {:intermediate-inputs [[2 2]] :nature [[1 3]] :labor [[2 5]]})
   (economy/worker-council 1 2 18 {:intermediate-inputs [[1 4]] :nature [[2 6]] :labor [[1 2]]})
   (economy/worker-council 2 1 7 {:intermediate-inputs [[1 1] [2 2]] :nature [[1 2]] :labor [[2 3]]})
   (economy/worker-council 2 2 9 {:intermediate-inputs [[2 5]] :nature [[2 1]] :labor [[1 6]]})])

(def consumer-councils
  "Two consumer councils. Private demand per commodity is 10+20=30 and 30+40=70; public demand
  per commodity is 4+6=10 and 8+12=20."
  [(economy/consumer-council [10 30] [4 8])
   (economy/consumer-council [20 40] [6 12])])

(def natural-resources-supply [40.0 30.0])

(def labor-supply [20.0 25.0])

(def industry-of
  "The `:industry` code of the worker councils that supply each produced category."
  {:private-goods 0 :intermediate-inputs 1 :public-goods 2})

(def input-keys
  "For each input category, the worker-council keys holding the inputs and their quantities."
  {:intermediate-inputs [:intermediate-inputs :intermediate-input-quantities]
   :nature [:nature :nature-quantities]
   :labor [:labor :labor-quantities]})

(defn- supply-of
  "Supply of commodity `id` of `category`, summed here from the inputs."
  [category id]
  (case category
    :nature (nth natural-resources-supply (dec id))
    :labor (nth labor-supply (dec id))
    (reduce + (for [wc worker-councils
                    :when (and (= (industry-of category) (:industry wc)) (= id (:product wc)))]
                (:output wc)))))

(defn- consumer-demand
  "Sum over consumer councils of the demand for the goods of `category` (`:private-goods` or
  `:public-goods`) that satisfy `keep?`."
  [category keep?]
  (reduce + (for [cc consumer-councils, good (category cc) :when (keep? good)] (:demand good))))

(defn- demand-of
  "Demand for commodity `id` of `category`, summed here from the inputs commodity by commodity.
  Public demand is divided by the number of consumer councils, as the program does."
  [category id]
  (case category
    :private-goods (consumer-demand category #(= id (:id %)))
    :public-goods (/ (consumer-demand category #(= id (:id %))) (count consumer-councils))
    (let [[inputs-key quantities-key] (input-keys category)]
      (reduce + (for [wc worker-councils
                      [input quantity] (map vector (inputs-key wc) (quantities-key wc))
                      :when (= id (:coefficient input))]
                  quantity)))))

(defn- category-wide-demand
  "Demand summed over every commodity of `category`, for the two consumer-good categories."
  [category]
  (case category
    :private-goods (consumer-demand category (constantly true))
    :public-goods (/ (consumer-demand category (constantly true)) (count consumer-councils))
    nil))

(defn- in-memory-step
  "Runs `update-surpluses-prices` once and prints its supply and demand per commodity."
  []
  (report/heading "Demand by commodity, part 1: pequod-plus.util/update-surpluses-prices (in-memory step)")
  (when-let [update-surpluses-prices (report/resolve-fn 'pequod-plus.util/update-surpluses-prices)]
    (let [price-data (economy/initial-price-data 2)
          result (update-surpluses-prices worker-councils consumer-councils natural-resources-supply
                                          labor-supply price-data economy/initial-price-delta-data false)
          rows (for [category economy/categories
                     entry (get result category)
                     side [:supply :demand]
                     :let [id (:id entry)
                           program (get entry side)
                           per-commodity (if (= side :supply) (supply-of category id) (demand-of category id))
                           category-wide (when (= side :demand) (category-wide-demand category))]]
                 [(name category) id (name side) program per-commodity category-wide
                  (report/yes-no program per-commodity) (report/yes-no program category-wide)])]
      (println "Two commodities per category, two consumer councils; pollutants off.")
      (println "program = value in the map returned by update-surpluses-prices;")
      (println "per_commodity = sum over councils of the quantities of this commodity id (computed in probe.demand-by-commodity);")
      (println "category_wide = sum over councils and over every commodity of the category (computed in probe.demand-by-commodity).")
      (println (str "match columns compare with relative tolerance " report/match-tolerance "."))
      (println)
      (report/print-table ["category" "id" "side" "program" "per_commodity" "category_wide"
                           "program=per_commodity" "program=category_wide"]
                          rows))))

;; ---------------------------------------------------------------------------------------------
;; Part 2: SQLite step

(def ^:private sqlite-categories
  "Price table, per-commodity supply query and per-commodity demand query for each category.
  Supply and demand queries return rows of (id, value)."
  [{:category "private-goods" :prices "private_good_prices"
    :supply "SELECT product AS id, SUM(output) AS v FROM wcs WHERE industry = 0 GROUP BY product"
    :demand "SELECT good_id AS id, SUM(demand) AS v FROM private_goods GROUP BY good_id"
    :category-wide "SELECT SUM(demand) AS v FROM private_goods"}
   {:category "intermediate-inputs" :prices "intermediate_input_prices"
    :supply "SELECT product AS id, SUM(output) AS v FROM wcs WHERE industry = 1 GROUP BY product"
    :demand "SELECT coefficient AS id, SUM(quantity) AS v FROM intermediate_inputs GROUP BY coefficient"}
   {:category "nature" :prices "nature_prices"
    :supply "SELECT id, natural_resource_supply AS v FROM natural_resources_supply"
    :demand "SELECT coefficient AS id, SUM(quantity) AS v FROM nature GROUP BY coefficient"}
   {:category "labor" :prices "labor_prices"
    :supply "SELECT id, labor_supply AS v FROM labor_supply"
    :demand "SELECT coefficient AS id, SUM(quantity) AS v FROM labor GROUP BY coefficient"}
   {:category "public-goods" :prices "public_good_prices"
    :supply "SELECT product AS id, SUM(output) AS v FROM wcs WHERE industry = 2 GROUP BY product"
    :demand "SELECT good_id AS id, SUM(demand) / (SELECT COUNT(*) FROM ccs) AS v FROM public_goods GROUP BY good_id"
    :category-wide "SELECT SUM(demand) / (SELECT COUNT(*) FROM ccs) AS v FROM public_goods"}])

(def ^:private shown-ids
  "Commodity ids printed row by row; the summary lines cover all 100."
  #{1 2 3 100})

(defn- by-id
  "Rows of (id, v) from `sql` as a map id -> v."
  [query ds sql]
  (into {} (map (juxt :id :v)) (query ds [sql])))

(defn- sqlite-category-rows
  "Row-by-row comparison and summary counts for one category, read after the round."
  [query ds {:keys [category prices supply demand category-wide]}]
  (let [program (into {} (map (juxt :id identity)) (query ds [(str "SELECT id, supply, demand FROM " prices)]))
        supply-by-id (by-id query ds supply)
        demand-by-id (by-id query ds demand)
        wide (when category-wide (:v (first (query ds [category-wide]))))
        compared (for [id (sort (keys program))
                       side [:supply :demand]
                       :let [value (get-in program [id side])
                             per-commodity (get (if (= side :supply) supply-by-id demand-by-id) id)
                             wide-value (when (= side :demand) wide)]]
                   {:row [category id (name side) value per-commodity wide-value
                          (report/yes-no value per-commodity) (report/yes-no value wide-value)]
                    :id id :side side
                    :per-commodity? (report/close? value per-commodity)
                    :wide? (report/close? value wide-value)})
        count-of (fn [side pred] (count (filter #(and (= side (:side %)) (pred %)) compared)))]
    {:rows (map :row (filter #(shown-ids (:id %)) compared))
     :summary (for [side [:supply :demand]]
                [category (name side) (count-of side (constantly true))
                 (count-of side :per-commodity?) (count-of side :wide?)])}))

(defn- sqlite-step
  "Builds the SQLite economy, runs one round of `iterate-plan-improved` and prints its supply and
  demand per commodity next to per-commodity sums over the rows the round wrote."
  []
  (report/heading "Demand by commodity, part 2: pequod-plus.csvgen/iterate-plan-improved (SQLite step)")
  (when-let [iterate-plan-improved (report/resolve-fn 'pequod-plus.csvgen/iterate-plan-improved)]
    (let [build! (report/resolve-fn 'probe.sqlite-economy/build!)
          query (report/resolve-fn 'probe.sqlite-economy/query)
          get-demand-sum (report/resolve-fn 'pequod-plus.csvgen/get-demand-sum)
          ds (build!)
          _ (iterate-plan-improved)
          results (map #(sqlite-category-rows query ds %) sqlite-categories)]
      (println "100 commodities per category (at 44a6d08 the program loops over ids 1 to 100), two consumer councils,")
      (println "300 worker councils with three inputs each; pollutants off; one round.")
      (println "program = supply and demand columns the round wrote to the price table;")
      (println "per_commodity = GROUP BY sum over the council rows the round wrote (query in probe.demand-by-commodity);")
      (println "category_wide = sum over all rows of the category (query in probe.demand-by-commodity).")
      (println (str "Rows for ids " (sort shown-ids) "; the summary covers every id."))
      (println)
      (report/print-table ["category" "id" "side" "program" "per_commodity" "category_wide"
                           "program=per_commodity" "program=category_wide"]
                          (mapcat :rows results))
      (println)
      (report/print-table ["category" "side" "commodities" "equal_to_per_commodity" "equal_to_category_wide"]
                          (mapcat :summary results))
      (println)
      (println "Sums returned by pequod-plus.csvgen/get-demand-sum after the round:")
      (report/print-table ["table" "get-demand-sum"]
                          (for [t [:private-goods :public-goods]] [(name t) (get-demand-sum ds t)])))))

(defn -main
  "Runs both parts."
  [& _]
  (in-memory-step)
  (sqlite-step)
  (shutdown-agents))
