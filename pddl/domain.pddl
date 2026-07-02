;; Smart EV Charging & Cabin Prep — PDDL 2.1 Numeric Domain
;; Compatible with ENHSP (Enhanced Numeric Heuristic Search Planner)
;; Group 22 — Smart Cities & IoT, University of Stuttgart, Summer 2026
;;
;; Design: single combined durative-actions (start+run+stop in one) for each
;; subsystem. This eliminates temporal-ordering issues between separate
;; start/effect/stop triplets and gives ENHSP a smaller search space.

(define (domain ev-cabin-prep)
  (:requirements :durative-actions :numeric-fluents :negative-preconditions)

  (:predicates
    (charging)          ;; charger is actively supplying current
    (hvac-on)           ;; cabin HVAC/heater is running
    (seat-warmer-on)    ;; seat warmer is active
    (lights-on)         ;; ambient LED lighting is on
    (route-loaded)      ;; navigation route has been loaded
    (charger-available) ;; physical charger is connected and not faulted
  )

  (:functions
    (battery-soc)             ;; current state of charge [%]
    (target-soc)              ;; desired SoC at departure [%]
    (cabin-temp)              ;; current cabin temperature [°C]
    (target-cabin-temp)       ;; desired cabin temperature at departure [°C]
    (outside-temp)            ;; ambient outside temperature [°C]
    (time-remaining)          ;; simulation minutes until departure deadline
    (total-power-draw)        ;; current aggregate power draw [W]
    (max-power)               ;; home circuit power budget [W]
    (charge-rate-pct-per-min) ;; SoC gain per sim-minute while charging [%/min]
    (hvac-power-w)            ;; HVAC power consumption [W]
    (seat-warmer-power-w)     ;; seat warmer power consumption [W]
    (charger-power-w)         ;; EV charger power consumption [W]
    (cooling-coeff)           ;; Newton cooling coefficient k [per sim-min]
    (heater-delta-per-min)    ;; cabin temp rise per sim-minute when HVAC on [°C/min]
  )

  ;; ------------------------------------------------------------------
  ;; Charge EV battery — combined start + charge + stop
  ;; Duration is the number of sim-minutes the charger runs.
  ;; Power budget check at start ensures we stay within home circuit limit.
  ;; ------------------------------------------------------------------
  (:durative-action charge-ev
    :parameters ()
    :duration (and (>= ?duration 1) (<= ?duration 120))
    :condition (and
      (at start (not (charging)))
      (at start (charger-available))
      (at start (< (battery-soc) (target-soc)))
      (at start (<= (+ (total-power-draw) (charger-power-w)) (max-power)))
      (at start (>= (time-remaining) ?duration))  ;; must finish before departure
    )
    :effect (and
      (at start (charging))
      (at start (increase (total-power-draw) (charger-power-w)))
      (at end (not (charging)))
      (at end (decrease (total-power-draw) (charger-power-w)))
      (at end (increase (battery-soc) (* ?duration (charge-rate-pct-per-min))))
    )
  )

  ;; ------------------------------------------------------------------
  ;; Heat cabin — combined start + heat + stop
  ;; Can overlap with charge-ev if charger-power-w + hvac-power-w <= max-power.
  ;; ------------------------------------------------------------------
  (:durative-action run-hvac
    :parameters ()
    :duration (and (>= ?duration 1) (<= ?duration 60))
    :condition (and
      (at start (not (hvac-on)))
      (at start (< (cabin-temp) (target-cabin-temp)))
      (at start (<= (+ (total-power-draw) (hvac-power-w)) (max-power)))
      (at start (>= (time-remaining) ?duration))  ;; must finish before departure
    )
    :effect (and
      (at start (hvac-on))
      (at start (increase (total-power-draw) (hvac-power-w)))
      (at end (not (hvac-on)))
      (at end (decrease (total-power-draw) (hvac-power-w)))
      (at end (increase (cabin-temp) (* ?duration (heater-delta-per-min))))
    )
  )

  ;; ------------------------------------------------------------------
  ;; Run seat warmer — comfort feature, very low power
  ;; ------------------------------------------------------------------
  (:durative-action warm-seat
    :parameters ()
    :duration (and (>= ?duration 1) (<= ?duration 15))
    :condition (and
      (at start (not (seat-warmer-on)))
      (at start (<= (+ (total-power-draw) (seat-warmer-power-w)) (max-power)))
    )
    :effect (and
      (at start (seat-warmer-on))
      (at start (increase (total-power-draw) (seat-warmer-power-w)))
      (at end (not (seat-warmer-on)))
      (at end (decrease (total-power-draw) (seat-warmer-power-w)))
    )
  )

  ;; ------------------------------------------------------------------
  ;; Turn on ambient lighting (duration=1: near-instant)
  ;; ------------------------------------------------------------------
  (:durative-action set-lights-on
    :parameters ()
    :duration (= ?duration 1)
    :condition (at start (not (lights-on)))
    :effect    (at end (lights-on))
  )

  ;; ------------------------------------------------------------------
  ;; Load navigation route into infotainment (duration=1: near-instant)
  ;; ------------------------------------------------------------------
  (:durative-action load-route
    :parameters ()
    :duration (= ?duration 1)
    :condition (at start (not (route-loaded)))
    :effect    (at end (route-loaded))
  )

)
