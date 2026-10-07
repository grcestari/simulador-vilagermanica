;; ============================================================
;; MODELO DE EVACUACAO EMERGENCIAL SOB BLACKOUT NOTURNO
;; Parque Vila Germanica - Blumenau, SC
;; ============================================================

breed [pedestrians pedestrian]
breed [staffs staff]

globals [
  evacuated-count
  total-evacuation-time
  evacuation-complete?
  tick-evacuated
  flow-rate
  exit-patches
  wall-patches
  dark-visibility
]

patches-own [
  is-wall?
  is-exit?
  sector-id
  exit-id
  pedestrian-density
  light-level
]

pedestrians-own [
  profile
  base-speed
  current-speed
  reaction-prob
  reacted?
  mobility-factor
  noise-factor
  target-exit
  following-staff?
  reaction-timer
  wall-follow-side
  in-wall-follow-mode?
]

staffs-own [
  lantern-range
  assigned-exit
]

to setup
  clear-all
  set evacuated-count 0
  set total-evacuation-time 0
  set evacuation-complete? false
  set tick-evacuated 0
  set flow-rate 0
  set dark-visibility 2

  setup-environment

  set exit-patches patches with [is-exit?]
  set wall-patches patches with [is-wall?]

  setup-pedestrians
  setup-staff

  update-patch-colors
  reset-ticks
end

to setup-environment
  ask patches [
    set is-wall? false
    set is-exit? false
    set sector-id 0
    set exit-id 0
    set pedestrian-density 0
    set light-level 0.0
  ]

  draw-outer-walls
  draw-internal-walls
  draw-exits
  draw-obstacles
  assign-sectors
end

to draw-outer-walls
  ask patches with [
    (pxcor >= 3 and pxcor <= 156 and pycor >= 3 and pycor <= 116) and
    (pxcor = 3 or pxcor = 156 or pycor = 3 or pycor = 116)
  ] [
    set is-wall? true
  ]
end

to draw-internal-walls
  ask patches with [pycor = 35 and pxcor >= 10 and pxcor <= 152] [ set is-wall? true ]
  ask patches with [pycor = 83 and pxcor >= 10 and pxcor <= 152] [ set is-wall? true ]
  ask patches with [pxcor = 10 and pycor >= 35 and pycor <= 83] [ set is-wall? true ]
  ask patches with [pxcor = 152 and pycor >= 35 and pycor <= 83] [ set is-wall? true ]
  
  ask patches with [
    pxcor = 83 and pycor >= 35 and pycor <= 83
    and not (pycor >= 45 and pycor <= 48)
    and not (pycor >= 58 and pycor <= 62)
    and not (pycor >= 73 and pycor <= 77)
  ] [ set is-wall? true ]

  ask patches with [
    (pxcor >= 15 and pxcor <= 52 and pycor >= 90 and pycor <= 112) and
    (pxcor = 15 or pxcor = 52 or pycor = 90 or pycor = 112)
  ] [ set is-wall? true ]

  ask patches with [
    (pxcor >= 70 and pxcor <= 119 and pycor >= 90 and pycor <= 112) and
    (pxcor = 70 or pxcor = 119 or pycor = 90 or pycor = 112)
  ] [ set is-wall? true ]

  ask patches with [
    (pxcor >= 15 and pxcor <= 64 and pycor >= 8 and pycor <= 22) and
    (pxcor = 15 or pxcor = 64 or pycor = 8 or pycor = 22)
  ] [ set is-wall? true ]

  ask patches with [
    (pxcor >= 95 and pxcor <= 134 and pycor >= 8 and pycor <= 25) and
    (pxcor = 95 or pxcor = 134 or pycor = 8 or pycor = 25)
  ] [ set is-wall? true ]
end

to draw-exits
  make-exit 25 28 35 35 1   
  make-exit 55 58 35 35 2   
  make-exit 40 43 83 83 3   
  make-exit 10 10 55 58 4   
  
  make-exit 100 103 35 35 5 
  make-exit 130 133 35 35 6 
  make-exit 110 113 83 83 7 
  make-exit 152 152 55 58 8 
  
  make-exit 30 33 90 90 9   
  make-exit 52 52 98 101 10 
  
  make-exit 88 91 90 90 11  
  make-exit 70 70 98 101 12 
  
  make-exit 30 40 8 8 13    
  make-exit 35 38 22 22 14  
  
  make-exit 110 113 8 8 15  
  make-exit 110 113 25 25 16 
end

to make-exit [x1 x2 y1 y2 eid]
  ask patches with [
    pxcor >= x1 and pxcor <= x2 and pycor >= y1 and pycor <= y2
  ] [
    set is-wall? false
    set is-exit? true
    set exit-id eid
  ]
end

to draw-obstacles
  make-obstacle 30 55 50 60
  make-obstacle 20 28 68 70
  make-obstacle 60 68 68 70
  
  make-obstacle 105 135 50 60
  make-obstacle 90 98 68 70
  make-obstacle 138 146 68 70
  
  make-obstacle 28 39 97 105
end

to make-obstacle [x1 x2 y1 y2]
  ask patches with [
    pxcor >= x1 and pxcor <= x2 and pycor >= y1 and pycor <= y2
  ] [
    set is-wall? true
  ]
end

to assign-sectors
  ask patches with [not is-wall? and not is-exit?] [
    ifelse pxcor > 10 and pxcor < 83 and pycor > 35 and pycor < 83 [ set sector-id 1 ] [
    ifelse pxcor > 83 and pxcor < 152 and pycor > 35 and pycor < 83 [ set sector-id 2 ] [
    ifelse pxcor > 15 and pxcor < 52 and pycor > 90 and pycor < 112 [ set sector-id 3 ] [
    ifelse pxcor > 70 and pxcor < 119 and pycor > 90 and pycor < 112 [ set sector-id 4 ] [
    ifelse pxcor > 15 and pxcor < 64 and pycor > 8 and pycor < 22 [ set sector-id 5 ] [
    ifelse pxcor > 95 and pxcor < 134 and pycor > 8 and pycor < 25 [ set sector-id 6 ] [
    ifelse pxcor > 3 and pxcor < 156 and pycor > 3 and pycor < 116 [ set sector-id 7 ] [
      set sector-id 0
    ]]]]]]]
  ]
end

to setup-pedestrians
  let actual-pop round (total-population / population-scale)
  let num-floor count patches with [not is-wall? and not is-exit? and sector-id > 0]
  if actual-pop > num-floor [ set actual-pop num-floor ]

  let pct-elderly-val 15
  let pct-sober-val (100 - pct-intoxicated - pct-elderly-val)
  if pct-sober-val < 0 [
    set pct-elderly-val max list 0 (100 - pct-intoxicated)
    set pct-sober-val 0
  ]

  let n-intox round (actual-pop * pct-intoxicated / 100)
  let n-elderly round (actual-pop * pct-elderly-val / 100)
  let n-sober (actual-pop - n-intox - n-elderly)
  if n-sober < 0 [ set n-sober 0 ]

  create-pedestrians n-sober [
    set profile "sober"
    set base-speed 1.4
    set reaction-prob 0.9
    set mobility-factor 1.0
    set noise-factor 5
    init-pedestrian
  ]

  create-pedestrians n-elderly [
    set profile "elderly"
    set base-speed 0.8
    set reaction-prob 0.7
    set mobility-factor 0.6
    set noise-factor 8
    init-pedestrian
  ]

  create-pedestrians n-intox [
    set profile "intoxicated"
    set base-speed 1.2
    set reaction-prob 0.5
    set mobility-factor 0.85
    set noise-factor 25
    init-pedestrian
  ]

  let floor-patches patches with [not is-wall? and not is-exit? and sector-id > 0]
  ask pedestrians [
    let p one-of floor-patches with [not any? pedestrians-here]
    if p = nobody [ set p one-of floor-patches ]
    move-to p
  ]
end

to init-pedestrian
  set current-speed 0
  set reacted? false
  set target-exit nobody
  set following-staff? false
  set reaction-timer 0
  set in-wall-follow-mode? false
  set wall-follow-side ifelse-value (random 2 = 0) [1] [-1]
  set heading random 360
  set size 0.8
  set shape "person"
  if profile = "sober" [ set color cyan ]
  if profile = "elderly" [ set color yellow ]
  if profile = "intoxicated" [ set color orange ]
end

to setup-staff
  if num-staff <= 0 [ stop ]
  let unique-exits remove-duplicates [exit-id] of exit-patches
  let n-exits length unique-exits
  if n-exits = 0 [ stop ]

  let base-per-exit floor (num-staff / n-exits)
  let extra num-staff mod n-exits

  foreach unique-exits [ eid ->
    let this-exit one-of exit-patches with [exit-id = eid]
    let n-here base-per-exit
    if extra > 0 [
      set n-here n-here + 1
      set extra extra - 1
    ]

    repeat n-here [
      create-staffs 1 [
        set lantern-range 8 + random 3
        set assigned-exit this-exit
        set color lime
        set size 1.5
        set shape "person"
        let cands patches with [
          not is-wall? and not is-exit? and sector-id > 0
          and distance this-exit >= 5 and distance this-exit <= 12
        ]
        ifelse any? cands [
          move-to one-of cands
        ] [
          move-to one-of patches with [
            not is-wall? and not is-exit? and sector-id > 0
          ]
        ]
      ]
    ]
  ]
end

to go
  if count pedestrians = 0 [
    set evacuation-complete? true
    set total-evacuation-time ticks
    stop
  ]
  if ticks >= 3600 [
    set total-evacuation-time 3600
    stop
  ]

  set tick-evacuated 0
  update-densities
  ask pedestrians [ pedestrian-step ]
  set flow-rate tick-evacuated

  if ticks mod 10 = 0 [ update-patch-colors ]
  tick
end

to update-densities
  ask patches with [not is-wall?] [
    let n (count pedestrians-here + count pedestrians-on neighbors)
    set pedestrian-density (n * population-scale) / 9
  ]
end

to pedestrian-step
  if not reacted? [
    react-to-blackout
    if not reacted? [ stop ]
  ]
  calculate-speed
  if current-speed <= 0.01 [ stop ]
  navigate
  move-forward-carefully
  check-exit-arrival
end

to react-to-blackout
  if ticks = 0 [
    ifelse random-float 1.0 < reaction-prob [
      set reacted? true
    ] [
      set reaction-timer 2 + random 14
    ]
    stop
  ]
  if reaction-timer > 0 [
    set reaction-timer reaction-timer - 1
    if any? (pedestrians in-radius 2) with [reacted?] [
      if random-float 1.0 < 0.3 [
        set reaction-timer 0
      ]
    ]
  ]
  if reaction-timer <= 0 and ticks > 0 [
    set reacted? true
  ]
end

to calculate-speed
  let k [pedestrian-density] of patch-here
  let s-dark darkness-factor
  let f-k density-speed-factor k
  set current-speed base-speed * s-dark * f-k * mobility-factor
  if current-speed < 0 [ set current-speed 0 ]
end

to-report density-speed-factor [k]
  if k <= 1.5 [ report 1.0 ]
  if k <= 3.0 [ report 1.0 - 0.15 * (k - 1.5) ]
  if k <= 6.0 [ report max list 0.05 (exp (- (k - 3.0))) ]
  report 0
end

to navigate
  set following-staff? false
  if try-follow-staff [ stop ]
  if try-detect-exit [ stop ]
  if wall-nearby? [
    do-wall-following
    stop
  ]
  do-herding
end

to-report try-follow-staff
  let nearby staffs in-radius 12
  if not any? nearby [ report false ]
  let closest min-one-of nearby [distance myself]
  if distance closest > [lantern-range] of closest [ report false ]
  set following-staff? true
  set target-exit [assigned-exit] of closest
  set in-wall-follow-mode? false
  face target-exit
  rt random-normal 0 (noise-factor / 2)
  report true
end

to-report try-detect-exit
  let vis exit-patches in-radius dark-visibility
  if not any? vis [ report false ]
  set target-exit min-one-of vis [distance myself]
  set in-wall-follow-mode? false
  face target-exit
  rt random-normal 0 (noise-factor / 3)
  report true
end

to-report wall-nearby?
  report any? (patches in-radius 1.5) with [is-wall?]
end

to do-wall-following
  set in-wall-follow-mode? true
  let ahead-patch patch-ahead 1
  ifelse ahead-patch = nobody or [is-wall?] of ahead-patch [
    let turn-angle (- wall-follow-side) * 45
    let tries 0
    while [tries < 8] [
      rt turn-angle
      let next-patch patch-ahead 1
      if next-patch != nobody and not [is-wall?] of next-patch [
        set tries 8
      ]
      set tries tries + 1
    ]
  ] [
    let side-patch patch-at-heading-and-distance (heading + wall-follow-side * 90) 1
    if side-patch = nobody or (side-patch != nobody and not [is-wall?] of side-patch) [
      rt wall-follow-side * 45
    ]
  ]
  rt random-normal 0 (noise-factor * 0.3)
end

to do-herding
  let moving-neighbors (pedestrians in-radius 3) with [
    reacted? and current-speed > 0.1
  ]
  ifelse any? moving-neighbors [
    let avg-dx mean [sin heading] of moving-neighbors
    let avg-dy mean [cos heading] of moving-neighbors
    if (abs avg-dx > 0.01 or abs avg-dy > 0.01) [
      let target-heading atan avg-dx avg-dy
      let angle-diff subtract-headings target-heading heading
      rt angle-diff * 0.5
    ]
  ] [
    rt random-normal 0 30
  ]
  rt random-normal 0 noise-factor
end

to move-forward-carefully
  let move-dist current-speed
  if move-dist > 1.0 [ set move-dist 1.0 ]
  let target-patch patch-ahead move-dist
  ifelse target-patch != nobody and can-move-to-patch? target-patch [
    fd move-dist
  ] [
    let moved? false
    foreach (list 30 -30 60 -60 90 -90 120 -120) [ angle ->
      if not moved? [
        let alt patch-at-heading-and-distance (heading + angle) move-dist
        if alt != nobody and can-move-to-patch? alt [
          rt angle
          fd move-dist
          set moved? true
        ]
      ]
    ]
  ]
end

to-report can-move-to-patch? [p]
  if p = nobody [ report false ]
  if [is-wall?] of p [ report false ]
  let max-agents max list 1 floor (6.0 / population-scale)
  if count pedestrians-on p >= max-agents [ report false ]
  report true
end

to check-exit-arrival
  if [is-exit?] of patch-here [
    set evacuated-count evacuated-count + population-scale
    set tick-evacuated tick-evacuated + population-scale
    die
  ]
end

to update-patch-colors
  ask patches [
    ifelse is-wall? [
      set pcolor gray + 2
    ] [
      ifelse is-exit? [
        set pcolor green + 1
      ] [
        ifelse pedestrian-density > 0.5 [
          set pcolor scale-color red pedestrian-density 8 0
        ] [
          ifelse sector-id > 0 [
            set pcolor black + 1
          ] [
            set pcolor black
          ]
        ]
      ]
    ]
  ]
end

to-report remaining-pedestrians
  report count pedestrians * population-scale
end

to-report current-flow-rate
  report flow-rate
end

to-report evacuation-time-display
  ifelse evacuation-complete? [
    report total-evacuation-time
  ] [
    report ticks
  ]
end

@#$#@#$#@
GRAPHICS-WINDOW
210
10
864
504
-1
-1
4.0
1
10
1
1
1
0
0
0
1
0
159
0
119
1
1
1
ticks
30.0

BUTTON
10
10
100
50
Setup
setup
NIL
1
T
OBSERVER
NIL
S
NIL
NIL
1

BUTTON
110
10
200
50
Go
go
T
1
T
OBSERVER
NIL
G
NIL
NIL
1

SLIDER
10
60
200
93
total-population
total-population
1000.0
40000.0
5000.0
1000.0
1
pessoas
HORIZONTAL

SLIDER
10
100
200
133
population-scale
population-scale
1.0
20.0
5.0
1.0
1
:1
HORIZONTAL

SLIDER
10
140
200
173
pct-intoxicated
pct-intoxicated
0.0
60.0
25.0
5.0
1
%
HORIZONTAL

SLIDER
10
180
200
213
num-staff
num-staff
0.0
50.0
10.0
1.0
1
NIL
HORIZONTAL

SLIDER
10
220
200
253
darkness-factor
darkness-factor
0.1
1.0
0.55
0.05
1
NIL
HORIZONTAL

MONITOR
835
10
1020
55
Evacuated Pedestrians
evacuated-count
0
1
11

MONITOR
835
65
1020
110
Remaining Pedestrians
remaining-pedestrians
0
1
11

MONITOR
835
120
1020
165
Total Evacuation Time (s)
evacuation-time-display
0
1
11

MONITOR
835
175
1020
220
Flow Rate Q(t) [ped/s]
current-flow-rate
1
1
11

MONITOR
835
230
1020
275
Sober Count
count pedestrians with [profile = "sober"] * population-scale
0
1
9

MONITOR
835
285
1020
330
Elderly Count
count pedestrians with [profile = "elderly"] * population-scale
0
1
9

MONITOR
835
340
1020
385
Intoxicated Count
count pedestrians with [profile = "intoxicated"] * population-scale
0
1
9

PLOT
10
530
500
720
Evacuation Curve
Time (s)
Remaining Pedestrians
0.0
3600.0
0.0
5000.0
true
true
"" ""
PENS
"remaining" 1.0 0 -13345367 true "" "plot count pedestrians * population-scale"

PLOT
510
530
1020
720
Flow Rate Q(t)
Time (s)
Ped/s
0.0
3600.0
0.0
50.0
true
true
"" ""
PENS
"Q(t)" 1.0 0 -2674135 true "" "plot flow-rate"

@#$#@#$#@
## MODELO DE EVACUAÇÃO EMERGENCIAL — VILA GERMÂNICA

### Contexto
Este modelo simula a evacuação de emergência de até 40.000 pessoas
no Parque Vila Germanica (Oktoberfest de Blumenau, SC) sob um
cenário de blackout noturno total e imprevisível.

### Abordagem
Modelagem Baseada em Agentes (ABM) com:
- **Física Social**: velocidade ajustada por densidade local
- **Navegação Tátil**: wall-following (regra da mão direita/esquerda)
- **Herding**: comportamento de manada por influência de vizinhos
- **Balizadores (Staff)**: orientação ativa por funcionários com lanternas

### Equação de Velocidade
```
v = v0 × S_dark × f(k) × s_mob
```
Onde:
- `v0` = velocidade livre do perfil (sóbrio: 1.4, idoso: 0.8, alcoolizado: 1.2 m/s)
- `S_dark` = fator de escuridão (slider `darkness-factor`, 0.55 recomendado)
- `f(k)` = fator de adensamento (decai exponencialmente acima de 3 ped/m²)
- `s_mob` = fator de mobilidade (sóbrio: 1.0, idoso: 0.6, alcoolizado: 0.85)

### Perfis de Pedestres
| Perfil | v0 | Reação | s_mob | Ruído Angular |
|---|---|---|---|---|
| Sóbrio | 1.4 m/s | 90% | 1.0 | 5° |
| Idoso | 0.8 m/s | 70% | 0.6 | 8° |
| Alcoolizado | 1.2 m/s | 50% | 0.85 | 25° |

### Layout
4 setores (pavilhões), 12 portões de saída, palcos e barracas como
obstáculos internos, corredores com aberturas para passagem entre setores.

### BehaviorSpace
Experimento fatorial pré-configurado:
- 3 níveis de % alcoolizados (10%, 25%, 40%)
- 3 níveis de balizadores (0, 10, 25)
- 30 repetições estocásticas por cenário
- Total: 270 execuções

### Referência
Gabriel Cestari & Thomas Haskel — Evacuação emergencial sob blackout
noturno no Parque Vila Germanica.
@#$#@#$#@
default
true
0
Polygon -7500403 true true 150 5 40 250 150 205 260 250

person
false
0
Circle -7500403 true true 110 5 80
Polygon -7500403 true true 105 90 120 195 90 285 105 300 135 300 150 225 165 300 195 300 210 285 180 195 195 90
Rectangle -7500403 true true 127 79 172 94
Polygon -7500403 true true 195 90 240 150 225 180 165 105
Polygon -7500403 true true 105 90 60 150 75 180 135 105

@#$#@#$#@
NetLogo 6.4.0
@#$#@#$#@
@#$#@#$#@
@#$#@#$#@
<experiments>
  <experiment name="factorial-evacuation-9scenarios" repetitions="30" runMetricsEveryStep="true">
    <setup>setup</setup>
    <go>go</go>
    <timeLimit steps="3600"/>
    <metric>ticks</metric>
    <metric>evacuated-count</metric>
    <metric>remaining-pedestrians</metric>
    <metric>flow-rate</metric>
    <metric>count pedestrians with [profile = "sober"]</metric>
    <metric>count pedestrians with [profile = "elderly"]</metric>
    <metric>count pedestrians with [profile = "intoxicated"]</metric>
    <enumeratedValueSet variable="total-population">
      <value value="5000"/>
    </enumeratedValueSet>
    <enumeratedValueSet variable="population-scale">
      <value value="5"/>
    </enumeratedValueSet>
    <enumeratedValueSet variable="pct-intoxicated">
      <value value="10"/>
      <value value="25"/>
      <value value="40"/>
    </enumeratedValueSet>
    <enumeratedValueSet variable="num-staff">
      <value value="0"/>
      <value value="10"/>
      <value value="25"/>
    </enumeratedValueSet>
    <enumeratedValueSet variable="darkness-factor">
      <value value="0.55"/>
    </enumeratedValueSet>
  </experiment>
</experiments>
@#$#@#$#@
@#$#@#$#@
@#$#@#$#@
default
0.0
-0.2 0 0.0 1.0
0.0 1 1.0 0.0
0.2 0 0.0 1.0
link direction
true
0
Line -7500403 true 150 150 90 180
Line -7500403 true 150 150 210 180

@#$#@#$#@
1
