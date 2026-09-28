(ns probe.sqlite-economy
  "A small economy in the SQLite file that `pequod-plus.csvgen` reads and writes.

  The tables are created by the program's own `pequod-plus.datasource` functions. The rows are
  inserted here: the program's generator (`pequod-plus.populate`) writes 30,000 councils drawn
  with an unseeded random generator, which cannot be checked by hand.

  At 44a6d08, `update-surpluses-prices-improved` takes supply and demand for commodity ids 1 to
  100 in every category from SQL sums, which are NULL for an id without a supplier or a user.
  The program reads the file
  `pequod-csv-test.db` in the working directory. The economy therefore has 100 commodities per
  category, two consumer councils, and one worker council for each of the 300 produced goods;
  the council producing good n of any industry uses intermediate input n, natural resource n and
  kind of labour n."
  (:require [clojure.java.io :as io]
            [next.jdbc :as jdbc]
            [next.jdbc.result-set :as result-set]
            [pequod-plus.datasource :as datasource]))

(def db-file
  "The file name `pequod-plus.csvgen` opens relative to the working directory."
  "pequod-csv-test.db")

(def goods-per-category 100)

(def initial-price 700.0)

(def consumer-council-income 5000.0)

(defn private-exponent
  "Utility exponent of private good `good` for consumer council `cc` (1 or 2)."
  [cc good]
  (+ (* cc 0.002) (* good 0.00002)))

(defn public-exponent
  "Utility exponent of public good `good` for consumer council `cc` (1 or 2)."
  [cc good]
  (+ (* cc 0.001) (* good 0.00003)))

(defn datasource
  "A next.jdbc datasource for `db-file`."
  []
  (jdbc/get-datasource {:dbtype "sqlite" :dbname db-file}))

(defn query
  "Runs `sql-params` and returns the rows as maps with unqualified lower-case keys."
  [ds sql-params]
  (jdbc/execute! ds sql-params {:builder-fn result-set/as-unqualified-lower-maps}))

(defn- insert-prices!
  "Fills price table `table` with ids 1 to 100 at the initial price, as `populate/create-prices` does."
  [ds table]
  (doseq [id (range 1 (inc goods-per-category))]
    (jdbc/execute! ds [(str "INSERT INTO " table " (id, price, price_delta, price_delta_to_use, pd, supply, demand, surplus)"
                            " VALUES (?, ?, 0.05, NULL, 0.25, NULL, NULL, NULL)")
                       id initial-price])))

(defn- insert-consumer-councils!
  "Two consumer councils, each with a utility exponent for all 100 private and all 100 public goods."
  [ds]
  (doseq [cc [1 2]]
    (jdbc/execute! ds ["INSERT INTO ccs (id, cohort_region, income, positive_utility_from_income, negative_utility_from_exposure) VALUES (?, 1, ?, 0.11, 0.11)"
                       cc consumer-council-income])
    (doseq [good (range 1 (inc goods-per-category))]
      (jdbc/execute! ds ["INSERT INTO private_goods (cc_id, good_id, exponent, augment, demand) VALUES (?, ?, ?, 0, 0)"
                         cc good (private-exponent cc good)])
      (jdbc/execute! ds ["INSERT INTO public_goods (cc_id, good_id, exponent, augment, demand) VALUES (?, ?, ?, 0, 0)"
                         cc good (public-exponent cc good)]))))

(defn total-factor-productivity
  "Total factor productivity of the worker council producing `product` in `industry`.

  It rises slowly with the product number, so that supplies differ between commodities. The
  councils of industries 0 and 2 are more productive for even product numbers; they then use more
  of their inputs, so that at equal prices intermediate input n is in surplus for odd n and in
  shortage for even n."
  [industry product]
  (+ (if (and (#{0 2} industry) (even? product)) 6.5 5.0)
     (* 0.005 product)))

(defn- insert-worker-councils!
  "One worker council per (industry, product). Each has three inputs with exponent 0.25, so the
  program solves it with `solution-3`."
  [ds]
  (doseq [industry [0 1 2]
          product (range 1 (inc goods-per-category))]
    (let [wc-id (+ (* industry goods-per-category) product)]
      (jdbc/execute! ds ["INSERT INTO wcs (id, effort, industry, product, output, effort_elasticity, total_factor_productivity, disutility_of_effort_coefficient, disutility_of_effort_exponent) VALUES (?, 0, ?, ?, 0, 0.075, ?, 1, 3.5)"
                         wc-id industry product (total-factor-productivity industry product)])
      (doseq [[table id-column] [["intermediate_inputs" "intermediate_input_id"]
                                 ["nature" "nature_id"]
                                 ["labor" "labor_id"]]]
        (jdbc/execute! ds [(str "INSERT INTO " table " (wc_id, " id-column ", exponent, coefficient, augment, quantity) VALUES (?, 1, 0.25, ?, 0, 0)")
                           wc-id product])))))

(defn- insert-supplies!
  "Supply 1000 of every natural resource and kind of labour, as `populate/create-supplies` does."
  [ds]
  (doseq [id (range 1 (inc goods-per-category))]
    (jdbc/execute! ds ["INSERT INTO natural_resources_supply (id, natural_resource_supply) VALUES (?, 1000)" id])
    (jdbc/execute! ds ["INSERT INTO labor_supply (id, labor_supply) VALUES (?, 1000)" id])))

(defn build!
  "Deletes `db-file` if present and creates the economy described in the namespace docstring."
  []
  (io/delete-file db-file true)
  (let [ds (datasource)]
    (datasource/create-normalized-ccs-tables ds)
    (datasource/create-normalized-wcs-tables ds)
    (datasource/create-and-populate-price-delta-table ds)
    (jdbc/with-transaction [tx ds]
      (insert-consumer-councils! tx)
      (insert-worker-councils! tx)
      (insert-supplies! tx)
      (doseq [table ["private_good_prices" "public_good_prices" "intermediate_input_prices"
                     "nature_prices" "labor_prices"]]
        (insert-prices! tx table))
      (jdbc/execute! tx ["INSERT INTO pollutant_prices (id, price, price_delta, price_delta_to_use, pd, supply, demand, surplus) VALUES (1, 700, 0.05, NULL, 0.25, NULL, NULL, NULL)"]))
    ds))
