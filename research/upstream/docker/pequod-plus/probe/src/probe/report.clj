(ns probe.report
  "Printing and lookup helpers shared by the probes. Nothing here computes a quantity that is
  being checked."
  (:require [clojure.string :as str]))

(def match-tolerance
  "Relative tolerance of the `match` columns. The values on both sides are always printed."
  1e-12)

(defn resolve-fn
  "Returns the var named by the fully qualified symbol `sym`, or nil when its namespace does not
  load or does not define it. The reason for a nil result is printed, because a missing function
  is itself a finding about the commit under test."
  [sym]
  (try
    (or (requiring-resolve sym)
        (do (println (str "  not defined at this commit: " sym)) nil))
    (catch Throwable e
      (let [root (last (take-while some? (iterate #(.getCause ^Throwable %) e)))]
        (println (str "  " sym " cannot be loaded at this commit: "
                      (.getName (class root)) ": " (first (str/split-lines (str (.getMessage root)))))))
      nil)))

(defn num-str
  "Integers as they are, other numbers as the shortest decimal text that reads back as the same
  double; `-` for nil."
  [x]
  (cond (nil? x) "-"
        (integer? x) (str x)
        (number? x) (str (double x))
        :else (str x)))

(defn close?
  "True when `a` and `b` agree to `match-tolerance`, relative to the larger magnitude."
  [a b]
  (and (number? a) (number? b)
       (let [scale (max (Math/abs (double a)) (Math/abs (double b)) 1e-300)]
         (<= (/ (Math/abs (- (double a) (double b))) scale) match-tolerance))))

(defn yes-no
  "`yes` or `no` for a `close?` comparison; `-` when either side is not a number."
  [a b]
  (if (and (number? a) (number? b)) (if (close? a b) "yes" "no") "-"))

(defn print-table
  "Prints `rows` (sequences of cells) under `header` as left-aligned, space-padded columns."
  [header rows]
  (let [cells (map #(map num-str %) (cons header rows))
        widths (apply map (fn [& column] (apply max (map count column))) cells)
        line (fn [row] (str/trimr (str/join "  " (map (fn [w c] (format (str "%-" w "s") c)) widths row))))]
    (println (line (first cells)))
    (println (str/join "  " (map #(apply str (repeat % "-")) widths)))
    (doseq [row (rest cells)] (println (line row)))))

(defn heading
  "Prints a section heading."
  [text]
  (println)
  (println text)
  (println (apply str (repeat (count text) "="))))
