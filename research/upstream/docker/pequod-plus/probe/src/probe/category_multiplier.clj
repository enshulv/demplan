(ns probe.category-multiplier
  "Whether the step multiplier of pequod-plus is one value per category of goods.

  The program's step for commodity i is `force-to-one(get-delta(w_i, m))`, where
  w_i = 1.05 - 0.5^(|2 surplus_i| / (supply_i + demand_i)) and m is the multiplier. m comes from
  `calculate-price-deltas`, which the program calls once per category.

  Part 1 calls `calculate-price-deltas`, `get-delta` and `force-to-one` directly for a category of
  two commodities, in several combinations of surplus and shortage. Next to each step it prints
  the step the same two functions give when m is the commodity's own imbalance
  |surplus_i| / mean(supply_i, demand_i).
  Part 2 goes through the in-memory per-round path: `update-surpluses-prices`, then
  `update-price-deltas`, then `update-surpluses-prices` again with the multipliers it returned.
  Part 3 goes through the SQLite per-round path: two rounds of `iterate-plan-improved`.
  Parts 2 and 3 check that the category value is the one applied to every commodity."
  (:require [probe.memory-economy :as economy]
            [probe.report :as report]))

(defn- imbalance
  "|surplus| / mean(supply, demand), the per-commodity form of the category multiplier."
  [supply demand]
  (/ (Math/abs (- supply demand)) (/ (+ supply demand) 2.0)))

(defn- signed-imbalance
  "surplus / mean(supply, demand), for display."
  [supply demand]
  (/ (- supply demand) (/ (+ supply demand) 2.0)))

(defn- base-delta
  "w = 1.05 - 0.5^(|2 surplus| / (supply + demand)), as on util.cljc line 195 at 44a6d08."
  [supply demand]
  (- 1.05 (Math/pow 0.5 (/ (Math/abs (* 2.0 (- supply demand))) (+ supply demand)))))

(def scenarios
  "Pairs of commodities in one category as [[supply demand] [supply demand]]."
  [["+20% and -20%" [[110.0 90.0] [90.0 110.0]]]
   ["+20% and +20% (control)" [[110.0 90.0] [110.0 90.0]]]
   ["-20% and -20% (control)" [[90.0 110.0] [90.0 110.0]]]
   ["+20% and +5%" [[110.0 90.0] [102.5 97.5]]]
   ["+20% and -5%" [[110.0 90.0] [97.5 102.5]]]
   ["+20% on 10 units, -1% on 1000 units" [[11.0 9.0] [995.0 1005.0]]]])

;; ---------------------------------------------------------------------------------------------
;; Part 1: the step functions

(defn- step-functions
  "Prints, per scenario and commodity, the category multiplier and both steps."
  []
  (report/heading "Category multiplier, part 1: calculate-price-deltas, get-delta, force-to-one")
  (let [calculate-price-deltas (report/resolve-fn 'pequod-plus.util/calculate-price-deltas)
        get-delta (report/resolve-fn 'pequod-plus.util/get-delta)
        force-to-one (report/resolve-fn 'pequod-plus.util/force-to-one)]
    (when (and calculate-price-deltas get-delta force-to-one)
      (println "category_m = calculate-price-deltas(supplies, demands, surpluses) of the two commodities;")
      (println "own_m = |surplus| / mean(supply, demand) of the commodity (computed in probe.category-multiplier);")
      (println "step = force-to-one(get-delta(w, m)) with the program's functions, w as on util.cljc line 195.")
      (println)
      (report/print-table
       ["scenario" "commodity" "supply" "demand" "imbalance" "category_m" "own_m"
        "step_with_category_m" "step_with_own_m"]
       (for [[label pairs] scenarios
             :let [supplies (map first pairs)
                   demands (map second pairs)
                   category-m (calculate-price-deltas supplies demands (map - supplies demands))]
             [i [s d]] (map-indexed vector pairs)
             :let [w (base-delta s d)
                   own-m (imbalance s d)]]
         [label (inc i) s d (signed-imbalance s d) category-m own-m
          (force-to-one (get-delta w category-m)) (force-to-one (get-delta w own-m))])))))

;; ---------------------------------------------------------------------------------------------
;; Part 2: in-memory per-round path

(defn- scenario-economy
  "An economy whose two intermediate inputs have the supplies and demands of `pairs`; every other
  commodity has a small positive supply and demand so that no ratio is 0/0."
  [pairs]
  (let [[[s1 d1] [s2 d2]] pairs]
    {:wcs [(economy/worker-council 0 1 10 {:intermediate-inputs [[1 d1] [2 d2]] :nature [[1 1]] :labor [[1 1]]})
           (economy/worker-council 0 2 10 {:nature [[2 1]] :labor [[2 1]]})
           (economy/worker-council 1 1 s1 {:nature [[1 1]] :labor [[1 1]]})
           (economy/worker-council 1 2 s2 {:nature [[2 1]] :labor [[2 1]]})
           (economy/worker-council 2 1 5 {:nature [[1 1]] :labor [[1 1]]})
           (economy/worker-council 2 2 5 {:nature [[2 1]] :labor [[2 1]]})]
     :ccs [(economy/consumer-council [4 4] [2 2]) (economy/consumer-council [4 4] [2 2])]
     :natural-resources-supply [4.0 4.0]
     :labor-supply [4.0 4.0]}))

(defn- in-memory-path
  "Runs two in-memory rounds per scenario and prints the steps the second round applied."
  []
  (report/heading "Category multiplier, part 2: in-memory path (update-surpluses-prices, update-price-deltas)")
  (let [update-surpluses-prices (report/resolve-fn 'pequod-plus.util/update-surpluses-prices)
        get-pricing-data (report/resolve-fn 'pequod-plus.util/get-pricing-data)
        update-price-deltas (report/resolve-fn 'pequod-plus.util/update-price-deltas)
        get-delta (report/resolve-fn 'pequod-plus.util/get-delta)
        force-to-one (report/resolve-fn 'pequod-plus.util/force-to-one)]
    (when (and update-surpluses-prices get-pricing-data update-price-deltas get-delta force-to-one)
      (println "Round 1: update-surpluses-prices; update-price-deltas on its supply, demand and surplus data.")
      (println "Round 2: update-surpluses-prices with those multipliers and round 1's prices; quantities unchanged.")
      (println "applied_step = :pd of the intermediate input in round 2's result;")
      (println "with_category_m / with_own_m = force-to-one(get-delta(w, m)), w = round 2's :price-delta-to-use.")
      (println)
      (report/print-table
       ["scenario" "commodity" "round1_supply" "round1_demand" "category_m" "own_m" "applied_step"
        "with_category_m" "with_own_m" "applied=category" "applied=own"]
       (for [[label pairs] scenarios
             :let [{:keys [wcs ccs natural-resources-supply labor-supply]} (scenario-economy pairs)
                   round-1 (update-surpluses-prices wcs ccs natural-resources-supply labor-supply
                                                    (economy/initial-price-data 2)
                                                    economy/initial-price-delta-data false)
                   multipliers (update-price-deltas (get-pricing-data round-1 :supply false)
                                                    (get-pricing-data round-1 :demand false)
                                                    (get-pricing-data round-1 :surplus false)
                                                    false)
                   round-2 (update-surpluses-prices wcs ccs natural-resources-supply labor-supply
                                                    round-1 multipliers false)
                   category-m (:intermediate-inputs multipliers)]
             [first-round second-round] (map vector (:intermediate-inputs round-1) (:intermediate-inputs round-2))
             :let [own-m (imbalance (:supply first-round) (:demand first-round))
                   w (:price-delta-to-use second-round)
                   with-category (force-to-one (get-delta w category-m))
                   with-own (force-to-one (get-delta w own-m))
                   applied (:pd second-round)]]
         [label (:id first-round) (:supply first-round) (:demand first-round) category-m own-m applied
          with-category with-own (report/yes-no applied with-category) (report/yes-no applied with-own)])))))

;; ---------------------------------------------------------------------------------------------
;; Part 3: SQLite per-round path

(def ^:private sqlite-shown-ids #{1 2 3 100})

(defn- sqlite-path
  "Runs two rounds of `iterate-plan-improved` on the SQLite economy and compares the steps of the
  second round with the category multiplier the first round stored."
  []
  (report/heading "Category multiplier, part 3: SQLite path (two rounds of iterate-plan-improved)")
  (let [iterate-plan-improved (report/resolve-fn 'pequod-plus.csvgen/iterate-plan-improved)
        price-delta-data (report/resolve-fn 'pequod-plus.csvgen/price-delta-data)
        get-delta (report/resolve-fn 'pequod-plus.util/get-delta)
        force-to-one (report/resolve-fn 'pequod-plus.util/force-to-one)]
    (when (and iterate-plan-improved price-delta-data get-delta force-to-one)
      (let [build! (report/resolve-fn 'probe.sqlite-economy/build!)
            query (report/resolve-fn 'probe.sqlite-economy/query)
            ds (build!)
            read-table (fn [] (into (sorted-map) (map (juxt :id identity))
                                    (query ds ["SELECT id, supply, demand, surplus, pd, price_delta_to_use FROM intermediate_input_prices"])))
            _ (iterate-plan-improved)
            round-1 (read-table)
            multipliers @@price-delta-data
            category-m (:intermediate-inputs multipliers)
            _ (iterate-plan-improved)
            round-2 (read-table)
            compared (for [[id first-round] round-1
                           :let [second-round (get round-2 id)
                                 own-m (imbalance (:supply first-round) (:demand first-round))
                                 w (:price_delta_to_use second-round)
                                 with-category (force-to-one (get-delta w category-m))
                                 with-own (force-to-one (get-delta w own-m))
                                 applied (:pd second-round)]]
                       {:id id
                        :row [id (signed-imbalance (:supply first-round) (:demand first-round)) category-m own-m
                              applied with-category with-own (report/yes-no applied with-category)
                              (report/yes-no applied with-own)]
                        :category? (report/close? applied with-category)
                        :own? (report/close? applied with-own)})]
        (println "Category: intermediate inputs (the program's supply and demand for them are per commodity).")
        (println "category_m = csvgen/price-delta-data after round 1 (written by update-price-deltas-db);")
        (println "own_m = |surplus| / mean(supply, demand) of round 1 (computed in probe.category-multiplier);")
        (println "applied_step = pd column after round 2; with_* = force-to-one(get-delta(w, m)),")
        (println "w = price_delta_to_use column after round 2.")
        (println)
        (println "Multipliers stored after round 1:")
        (report/print-table ["category" "m"] (for [[k v] (sort-by (comp name key) multipliers)] [(name k) v]))
        (println)
        (report/print-table ["id" "round1_imbalance" "category_m" "own_m" "applied_step" "with_category_m"
                             "with_own_m" "applied=category" "applied=own"]
                            (map :row (filter #(sqlite-shown-ids (:id %)) compared)))
        (println)
        (report/print-table ["commodities" "applied=category" "applied=own"]
                            [[(count compared) (count (filter :category? compared)) (count (filter :own? compared))]])))))

(defn -main
  "Runs all three parts."
  [& _]
  (step-functions)
  (in-memory-path)
  (sqlite-path)
  (shutdown-agents))
