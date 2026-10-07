;; ============================================================
;; MODELO DE EVACUAÃ‡ÃƒO EMERGENCIAL SOB BLACKOUT NOTURNO
;; Parque Vila GermÃ¢nica â€“ Oktoberfest de Blumenau, SC
;; Baseado no trabalho de Gabriel Cestari & Thomas Haskel
;;
;; Modelagem Baseada em Agentes (ABM) com:
;;   â€¢ FÃ­sica Social (velocidade ajustada por densidade)
;;   â€¢ NavegaÃ§Ã£o TÃ¡til (wall-following sob escuridÃ£o)
;;   â€¢ Comportamento de Manada (herding)
;;   â€¢ OrientaÃ§Ã£o por Balizadores (staff com lanternas)
;;
;; DiscretizaÃ§Ã£o: cada patch = 1 m Ã— 1 m
;; Temporalidade: cada tick  = 1 segundo
;; ============================================================

;; ===================== RAÃ‡AS ==============================
breed [pedestrians pedestrian]
breed [staffs staff]

;; ===================== GLOBAIS ============================
;; Sliders de interface (nÃ£o declarar aqui):
;;   total-population, population-scale, pct-intoxicated,
;;   num-staff, darkness-factor
globals [
  evacuated-count           ;; Total acumulado de evacuados (escala real)
  total-evacuation-time     ;; Tempo total de evacuaÃ§Ã£o (s / ticks)
  evacuation-complete?      ;; EvacuaÃ§Ã£o concluÃ­da?
  tick-evacuated            ;; Evacuados no tick corrente (escala real)
  flow-rate                 ;; VazÃ£o Q(t) em ped/s
  exit-patches              ;; Agentset de patches de saÃ­da
  wall-patches              ;; Agentset de patches de parede
  dark-visibility           ;; Alcance visual no escuro (â‰ˆ metros)
]

;; ===================== PATCHES ============================
patches-own [
  is-wall?                  ;; Parede / obstÃ¡culo fÃ­sico
  is-exit?                  ;; PortÃ£o / porta de saÃ­da
  sector-id                 ;; ID do setor (1â€“4; 0 = corredor / externo)
  exit-id                   ;; ID do portÃ£o de saÃ­da (1â€“12; 0 = nenhum)
  pedestrian-density        ;; Densidade local (ped/mÂ²)
  light-level               ;; NÃ­vel de iluminaÃ§Ã£o (0.0 = blackout total)
]

;; ===================== PEDESTRES ==========================
pedestrians-own [
  profile                   ;; "sober" | "elderly" | "intoxicated"
  base-speed                ;; vâ‚€ (m/s)
  current-speed             ;; v atual (m/s)
  reaction-prob             ;; Probabilidade de reaÃ§Ã£o imediata
  reacted?                  ;; JÃ¡ percebeu a emergÃªncia?
  mobility-factor           ;; s_mob
  noise-factor              ;; Amplitude de ruÃ­do angular (Â°)
  target-exit               ;; Patch da saÃ­da escolhida
  following-staff?          ;; Sendo guiado por balizador?
  reaction-timer            ;; Ticks restantes de latÃªncia
  wall-follow-side          ;; +1 (mÃ£o direita) ou âˆ’1 (mÃ£o esquerda)
  in-wall-follow-mode?      ;; NavegaÃ§Ã£o tÃ¡til ativa?
]

;; ===================== BALIZADORES ========================
staffs-own [
  lantern-range             ;; Raio de alcance da lanterna (m â‰ˆ patches)
  assigned-exit             ;; Patch do portÃ£o atribuÃ­do
]


;; ==========================================================
;; â–ˆâ–ˆâ–ˆâ–ˆâ–ˆâ–ˆâ–ˆâ–ˆâ–ˆâ–ˆâ–ˆâ–ˆâ–ˆâ–ˆâ–ˆâ–ˆâ–ˆâ–ˆ  S E T U P  â–ˆâ–ˆâ–ˆâ–ˆâ–ˆâ–ˆâ–ˆâ–ˆâ–ˆâ–ˆâ–ˆâ–ˆâ–ˆâ–ˆâ–ˆâ–ˆâ–ˆâ–ˆâ–ˆâ–ˆâ–ˆâ–ˆâ–ˆâ–ˆâ–ˆâ–ˆâ–ˆ
;; ==========================================================
to setup
  clear-all

  ;; --- Inicializa globais ---
  set evacuated-count 0
  set total-evacuation-time 0
  set evacuation-complete? false
  set tick-evacuated 0
  set flow-rate 0
  set dark-visibility 2       ;; â‰ˆ 2 m de visibilidade no blackout

  ;; --- ConstrÃ³i o ambiente fÃ­sico ---
  setup-environment

  ;; --- Cacheia agentsets frequentes ---
  set exit-patches patches with [is-exit?]
  set wall-patches patches with [is-wall?]

  ;; --- Semeia agentes ---
  setup-pedestrians
  setup-staff

  ;; --- Renderiza a visualizaÃ§Ã£o ---
  update-patch-colors

  reset-ticks
end


;; ==========================================================
;; CONSTRUÃ‡ÃƒO DO AMBIENTE FÃSICO
;; Malha 120 Ã— 100 patches  (pxcor 0â€“119, pycor 0â€“99)
;; Complexo inscrito entre x âˆˆ [5,114] e y âˆˆ [5,94]
;;
;; Layout (vista de cima):
;; â”Œâ”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€E5â”€â”€â”€â”€â”€E6â”€â”€â”¬â”€â”€E7â”€â”€â”€â”€â”€E8â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â” y=94
;; â”‚       SETOR 1         â”‚       SETOR 2          â”‚
;; â”‚  [Palco1] [Bar1]     â”‚  [Bar2] [Palco2]       â”‚
;; E10                     â”‚                      E12
;; â”‚       ===abertura===  â‰¡  ===abertura===        â”‚
;; â”œâ”€â”€â”€aberturaâ”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â‰¡â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€aberturaâ”€â”€â”€â”€â”¤ y=49
;; â”‚       ===abertura===  â‰¡  ===abertura===        â”‚
;; E9                      â”‚                      E11
;; â”‚  [Palco3] [Bar3]     â”‚  [Bar4] [Palco4]       â”‚
;; â”‚       SETOR 3         â”‚       SETOR 4          â”‚
;; â””â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€E1â”€â”€â”€â”€â”€E2â”€â”€â”´â”€â”€E3â”€â”€â”€â”€â”€E4â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”˜ y=5
;; x=5                    x=59                   x=114
;; ==========================================================
to setup-environment
  ;; Reseta todos os patches
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

;; ----------------------------------------------------------
;; Paredes externas do complexo
;; ----------------------------------------------------------
to draw-outer-walls
  ask patches with [
    (pxcor >= 5 and pxcor <= 114 and pycor >= 5 and pycor <= 94) and
    (pxcor = 5 or pxcor = 114 or pycor = 5 or pycor = 94)
  ] [
    set is-wall? true
  ]
end

;; ----------------------------------------------------------
;; DivisÃ³rias internas (com aberturas para passagem)
;; ----------------------------------------------------------
to draw-internal-walls
  ;; HORIZONTAL (y = 49) â€” separa setores superiores dos inferiores
  ;; Aberturas: x âˆˆ [25,30], [57,62], [85,90]
  ask patches with [
    pycor = 49 and pxcor >= 6 and pxcor <= 113
    and not (pxcor >= 25 and pxcor <= 30)
    and not (pxcor >= 57 and pxcor <= 62)
    and not (pxcor >= 85 and pxcor <= 90)
  ] [
    set is-wall? true
  ]

  ;; VERTICAL (x = 59) â€” separa setores esquerdos dos direitos
  ;; Aberturas: y âˆˆ [20,25], [47,51], [70,75]
  ask patches with [
    pxcor = 59 and pycor >= 6 and pycor <= 93
    and not (pycor >= 20 and pycor <= 25)
    and not (pycor >= 47 and pycor <= 51)
    and not (pycor >= 70 and pycor <= 75)
  ] [
    set is-wall? true
  ]
end

;; ----------------------------------------------------------
;; PortÃµes de saÃ­da (12 portÃµes, 4 patches de largura cada)
;; ----------------------------------------------------------
to draw-exits
  ;; --- LADO SUL (y = 5) ---
  make-exit 18  21   5   5   1      ;; E1  â€“ sudoeste        (S3)
  make-exit 42  45   5   5   2      ;; E2  â€“ sul-centro-esq  (S3)
  make-exit 74  77   5   5   3      ;; E3  â€“ sul-centro-dir  (S4)
  make-exit 98 101   5   5   4      ;; E4  â€“ sudeste         (S4)
  ;; --- LADO NORTE (y = 94) ---
  make-exit 18  21  94  94   5      ;; E5  â€“ noroeste        (S1)
  make-exit 42  45  94  94   6      ;; E6  â€“ norte-centro-esq(S1)
  make-exit 74  77  94  94   7      ;; E7  â€“ norte-centro-dir(S2)
  make-exit 98 101  94  94   8      ;; E8  â€“ nordeste        (S2)
  ;; --- LADO OESTE (x = 5) ---
  make-exit  5   5  25  28   9      ;; E9  â€“ oeste-inferior  (S3)
  make-exit  5   5  70  73  10      ;; E10 â€“ oeste-superior  (S1)
  ;; --- LADO LESTE (x = 114) ---
  make-exit 114 114  25  28  11     ;; E11 â€“ leste-inferior  (S4)
  make-exit 114 114  70  73  12     ;; E12 â€“ leste-superior  (S2)
end

;; UtilitÃ¡rio: marca uma faixa retangular como saÃ­da
to make-exit [x1 x2 y1 y2 eid]
  ask patches with [
    pxcor >= x1 and pxcor <= x2 and pycor >= y1 and pycor <= y2
  ] [
    set is-wall? false
    set is-exit? true
    set exit-id eid
  ]
end

;; ----------------------------------------------------------
;; ObstÃ¡culos internos (palcos e barracas de bebida)
;; ----------------------------------------------------------
to draw-obstacles
  ;; Palcos (um por setor â€” blocos intransponÃ­veis)
  make-obstacle 22 37 70 77       ;; Palco Setor 1
  make-obstacle 78 93 70 77       ;; Palco Setor 2
  make-obstacle 22 37 18 25       ;; Palco Setor 3
  make-obstacle 78 93 18 25       ;; Palco Setor 4
  ;; Barracas de bebida (balcÃµes menores)
  make-obstacle 40 50 58 60       ;; Barraca Setor 1
  make-obstacle 68 78 58 60       ;; Barraca Setor 2
  make-obstacle 40 50 35 37       ;; Barraca Setor 3
  make-obstacle 68 78 35 37       ;; Barraca Setor 4
end

to make-obstacle [x1 x2 y1 y2]
  ask patches with [
    pxcor >= x1 and pxcor <= x2 and pycor >= y1 and pycor <= y2
  ] [
    set is-wall? true
  ]
end

;; ----------------------------------------------------------
;; AtribuiÃ§Ã£o de setores aos patches livres
;; ----------------------------------------------------------
to assign-sectors
  ;; Setor 1 â€” superior esquerdo
  ask patches with [
    pxcor >= 6 and pxcor <= 58 and pycor >= 50 and pycor <= 93
    and not is-wall? and not is-exit?
  ] [ set sector-id 1 ]

  ;; Setor 2 â€” superior direito
  ask patches with [
    pxcor >= 60 and pxcor <= 113 and pycor >= 50 and pycor <= 93
    and not is-wall? and not is-exit?
  ] [ set sector-id 2 ]

  ;; Setor 3 â€” inferior esquerdo
  ask patches with [
    pxcor >= 6 and pxcor <= 58 and pycor >= 6 and pycor <= 48
    and not is-wall? and not is-exit?
  ] [ set sector-id 3 ]

  ;; Setor 4 â€” inferior direito
  ask patches with [
    pxcor >= 60 and pxcor <= 113 and pycor >= 6 and pycor <= 48
    and not is-wall? and not is-exit?
  ] [ set sector-id 4 ]
end


;; ==========================================================
;; CRIAÃ‡ÃƒO DOS PEDESTRES
;; ==========================================================
to setup-pedestrians
  let actual-pop round (total-population / population-scale)

  ;; Limita Ã  capacidade fÃ­sica do espaÃ§o
  let num-floor count patches with [not is-wall? and not is-exit? and sector-id > 0]
  if actual-pop > num-floor [ set actual-pop num-floor ]

  ;; --- ProporÃ§Ãµes de perfil ---
  ;; pct-intoxicated vem do slider; idosos fixados em 15 %
  let pct-elderly-val 15
  let pct-sober-val (100 - pct-intoxicated - pct-elderly-val)
  if pct-sober-val < 0 [
    set pct-elderly-val max list 0 (100 - pct-intoxicated)
    set pct-sober-val 0
  ]

  let n-intox  round (actual-pop * pct-intoxicated   / 100)
  let n-elderly round (actual-pop * pct-elderly-val   / 100)
  let n-sober  (actual-pop - n-intox - n-elderly)
  if n-sober < 0 [ set n-sober 0 ]

  ;; Cria pedestres SÃ“BRIOS
  create-pedestrians n-sober [
    set profile        "sober"
    set base-speed     1.4        ;; m/s
    set reaction-prob  0.9
    set mobility-factor 1.0
    set noise-factor   5          ;; graus
    init-pedestrian
  ]

  ;; Cria pedestres IDOSOS
  create-pedestrians n-elderly [
    set profile        "elderly"
    set base-speed     0.8
    set reaction-prob  0.7
    set mobility-factor 0.6
    set noise-factor   8
    init-pedestrian
  ]

  ;; Cria pedestres ALCOOLIZADOS
  create-pedestrians n-intox [
    set profile        "intoxicated"
    set base-speed     1.2
    set reaction-prob  0.5
    set mobility-factor 0.85
    set noise-factor   25         ;; ruÃ­do angular elevado
    init-pedestrian
  ]

  ;; Distribui nos patches de piso dentro dos setores
  let floor-patches patches with [not is-wall? and not is-exit? and sector-id > 0]
  ask pedestrians [
    let p one-of floor-patches with [not any? pedestrians-here]
    if p = nobody [ set p one-of floor-patches ]
    move-to p
  ]
end

;; InicializaÃ§Ã£o comum de cada pedestre (turtle context)
to init-pedestrian
  set current-speed      0
  set reacted?           false
  set target-exit        nobody
  set following-staff?   false
  set reaction-timer     0
  set in-wall-follow-mode? false
  set wall-follow-side   ifelse-value (random 2 = 0) [1] [-1]
  set heading            random 360
  set size               0.8
  set shape              "person"

  ;; Cor por perfil
  if profile = "sober"       [ set color cyan   ]
  if profile = "elderly"     [ set color yellow  ]
  if profile = "intoxicated" [ set color orange  ]
end


;; ==========================================================
;; CRIAÃ‡ÃƒO DOS BALIZADORES (STAFF)
;; ==========================================================
to setup-staff
  if num-staff <= 0 [ stop ]

  ;; Distribui staff proporcionalmente entre os portÃµes
  let unique-exits remove-duplicates [exit-id] of exit-patches
  let n-exits length unique-exits
  if n-exits = 0 [ stop ]

  let base-per-exit floor (num-staff / n-exits)
  let extra         num-staff mod n-exits

  foreach unique-exits [ eid ->
    let this-exit one-of exit-patches with [exit-id = eid]
    let n-here base-per-exit
    if extra > 0 [
      set n-here n-here + 1
      set extra  extra - 1
    ]

    repeat n-here [
      create-staffs 1 [
        set lantern-range  8 + random 3          ;; 8â€“10 m
        set assigned-exit  this-exit
        set color          lime
        set size           1.5
        set shape          "person"

        ;; Posiciona a 5â€“12 m da saÃ­da, dentro do complexo
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


;; ==========================================================
;; â–ˆâ–ˆâ–ˆâ–ˆâ–ˆâ–ˆâ–ˆâ–ˆâ–ˆâ–ˆâ–ˆâ–ˆâ–ˆâ–ˆâ–ˆâ–ˆâ–ˆâ–ˆ  G O  (LOOP)  â–ˆâ–ˆâ–ˆâ–ˆâ–ˆâ–ˆâ–ˆâ–ˆâ–ˆâ–ˆâ–ˆâ–ˆâ–ˆâ–ˆâ–ˆâ–ˆâ–ˆâ–ˆâ–ˆâ–ˆâ–ˆâ–ˆâ–ˆâ–ˆâ–ˆ
;; ==========================================================
to go
  ;; --- CondiÃ§Ãµes de parada ---
  if count pedestrians = 0 [
    set evacuation-complete?  true
    set total-evacuation-time ticks
    stop
  ]
  if ticks >= 3600 [
    set total-evacuation-time 3600
    stop
  ]

  ;; Reseta contador de tick
  set tick-evacuated 0

  ;; 1. Atualiza densidades locais
  update-densities

  ;; 2. Cada pedestre age (ordem aleatÃ³ria intrÃ­nseca do `ask`)
  ask pedestrians [ pedestrian-step ]

  ;; 3. Calcula vazÃ£o instantÃ¢nea Q(t) = evacuados neste tick
  set flow-rate tick-evacuated

  ;; 4. Atualiza visualizaÃ§Ã£o (a cada 10 ticks por desempenho)
  if ticks mod 10 = 0 [ update-patch-colors ]

  tick
end


;; ==========================================================
;; ATUALIZAÃ‡ÃƒO DE DENSIDADES  (vizinhanÃ§a de Moore = 9 mÂ²)
;; ==========================================================
to update-densities
  ask patches with [not is-wall?] [
    let n (count pedestrians-here + count pedestrians-on neighbors)
    set pedestrian-density (n * population-scale) / 9
  ]
end


;; ==========================================================
;; PASSO INDIVIDUAL DO PEDESTRE  (turtle context)
;; ==========================================================
to pedestrian-step
  ;; 1. Verifica / gerencia reaÃ§Ã£o ao blackout
  if not reacted? [
    react-to-blackout
    if not reacted? [ stop ]    ;; Ainda em hesitaÃ§Ã£o / pÃ¢nico
  ]

  ;; 2. Recalcula velocidade
  calculate-speed
  if current-speed <= 0.01 [ stop ]   ;; Travado por congestionamento

  ;; 3. Escolhe direÃ§Ã£o (navegaÃ§Ã£o)
  navigate

  ;; 4. Move com verificaÃ§Ã£o de colisÃ£o
  move-forward-carefully

  ;; 5. Verifica se alcanÃ§ou um portÃ£o de saÃ­da
  check-exit-arrival
end


;; ==========================================================
;; LATÃŠNCIA DE REAÃ‡ÃƒO AO BLACKOUT
;; ==========================================================
to react-to-blackout   ;; turtle context
  ;; --- Instante do apagÃ£o (t = 0) ---
  if ticks = 0 [
    ifelse random-float 1.0 < reaction-prob [
      set reacted? true
    ] [
      ;; Atribui tempo de latÃªncia estocÃ¡stico (2 a 15 s)
      set reaction-timer 2 + random 14
    ]
    stop
  ]

  ;; --- Ticks seguintes: decrementa timer ---
  if reaction-timer > 0 [
    set reaction-timer reaction-timer - 1

    ;; ContÃ¡gio social: vizinhos que jÃ¡ reagiram podem
    ;; antecipar a reaÃ§Ã£o deste agente (30 % de chance)
    if any? (pedestrians in-radius 2) with [reacted?] [
      if random-float 1.0 < 0.3 [
        set reaction-timer 0
      ]
    ]
  ]

  ;; Quando o timer zera, o agente reage
  if reaction-timer <= 0 and ticks > 0 [
    set reacted? true
  ]
end


;; ==========================================================
;; EQUAÃ‡ÃƒO DE VELOCIDADE AJUSTADA
;;   v = vâ‚€ Â· S_dark Â· f(k) Â· s_mob
;;
;; S_dark  = darkness-factor (slider 0.1â€“1.0; 0.55 recomendado)
;; f(k)    = fator de adensamento local
;; s_mob   = fator de mobilidade do perfil
;; ==========================================================
to calculate-speed   ;; turtle context
  let k      [pedestrian-density] of patch-here
  let s-dark darkness-factor
  let f-k    density-speed-factor k

  set current-speed base-speed * s-dark * f-k * mobility-factor
  if current-speed < 0 [ set current-speed 0 ]
end

;; Reporter: f(k) â€” fator velocidade Ã— densidade
to-report density-speed-factor [k]
  ;; Fluxo livre
  if k <= 1.5 [ report 1.0 ]
  ;; Decaimento linear moderado (1.5 < k â‰¤ 3.0)
  if k <= 3.0 [ report 1.0 - 0.15 * (k - 1.5) ]
  ;; Decaimento exponencial â€” congestionamento (3.0 < k â‰¤ 6.0)
  if k <= 6.0 [ report max list 0.05 (exp (- (k - 3.0))) ]
  ;; Jamming total (k > 6.0)
  report 0
end


;; ==========================================================
;; NAVEGAÃ‡ÃƒO SOB ESCURIDÃƒO
;; Prioridade:
;;   1) OrientaÃ§Ã£o por balizador (staff dentro do alcance)
;;   2) DetecÃ§Ã£o de saÃ­da por proximidade (< dark-visibility)
;;   3) Wall-following (navegaÃ§Ã£o tÃ¡til ao longo de paredes)
;;   4) Herding (seguir o fluxo de vizinhos em movimento)
;; ==========================================================
to navigate   ;; turtle context
  set following-staff? false

  ;; 1) Balizador
  if try-follow-staff [ stop ]

  ;; 2) SaÃ­da visÃ­vel
  if try-detect-exit [ stop ]

  ;; 3) Wall-following
  if wall-nearby? [
    do-wall-following
    stop
  ]

  ;; 4) Herding / caminhada aleatÃ³ria
  do-herding
end

;; --- (1) Tenta seguir balizador ---
to-report try-follow-staff   ;; turtle reporter
  let nearby staffs in-radius 12
  if not any? nearby [ report false ]

  let closest min-one-of nearby [distance myself]
  if distance closest > [lantern-range] of closest [ report false ]

  set following-staff?    true
  set target-exit         [assigned-exit] of closest
  set in-wall-follow-mode? false
  face target-exit
  rt random-normal 0 (noise-factor / 2)
  report true
end

;; --- (2) Tenta detectar saÃ­da prÃ³xima ---
to-report try-detect-exit   ;; turtle reporter
  let vis exit-patches in-radius dark-visibility
  if not any? vis [ report false ]

  set target-exit          min-one-of vis [distance myself]
  set in-wall-follow-mode? false
  face target-exit
  rt random-normal 0 (noise-factor / 3)
  report true
end


;; ==========================================================
;; WALL-FOLLOWING  (Regra da MÃ£o Direita / Esquerda)
;; ==========================================================
to-report wall-nearby?
  report any? (patches in-radius 1.5) with [is-wall?]
end

to do-wall-following   ;; turtle context
  set in-wall-follow-mode? true

  let ahead-patch patch-ahead 1

  ifelse ahead-patch = nobody or [is-wall?] of ahead-patch [
    ;; â–º Parede ou limite Ã  frente â†’ gira para o lado oposto
    let turn-angle (- wall-follow-side) * 45
    let tries 0
    while [tries < 8] [
      rt turn-angle
      let next-patch patch-ahead 1
      if next-patch != nobody and not [is-wall?] of next-patch [
        ;; DireÃ§Ã£o livre encontrada
        set tries 8   ;; sai do loop
      ]
      set tries tries + 1
    ]
  ] [
    ;; â–º Sem parede Ã  frente: verifica contato lateral
    let side-patch patch-at-heading-and-distance
        (heading + wall-follow-side * 90) 1

    if side-patch = nobody or
       (side-patch != nobody and not [is-wall?] of side-patch) [
      ;; Perdeu contato com a parede â†’ vira para reencontrar
      rt wall-follow-side * 45
    ]
  ]

  ;; RuÃ­do tÃ¡til (pequeno)
  rt random-normal 0 (noise-factor * 0.3)
end


;; ==========================================================
;; HERDING  (Comportamento de Manada)
;; ==========================================================
to do-herding   ;; turtle context
  let moving-neighbors (pedestrians in-radius 3) with [
    reacted? and current-speed > 0.1
  ]

  ifelse any? moving-neighbors [
    ;; MÃ©dia circular dos headings dos vizinhos
    let avg-dx mean [sin heading] of moving-neighbors
    let avg-dy mean [cos heading] of moving-neighbors

    if (abs avg-dx > 0.01 or abs avg-dy > 0.01) [
      let target-heading atan avg-dx avg-dy
      let angle-diff subtract-headings target-heading heading
      ;; Ajuste gradual (50 % da diferenÃ§a)
      rt angle-diff * 0.5
    ]
  ] [
    ;; Nenhum vizinho em movimento â†’ caminhada aleatÃ³ria
    rt random-normal 0 30
  ]

  ;; RuÃ­do de perfil
  rt random-normal 0 noise-factor
end


;; ==========================================================
;; MOVIMENTO COM VERIFICAÃ‡ÃƒO DE COLISÃƒO
;; ==========================================================
to move-forward-carefully   ;; turtle context
  let move-dist current-speed
  ;; Limita a 1 patch/tick para evitar travessia de paredes
  if move-dist > 1.0 [ set move-dist 1.0 ]

  ;; Tenta avanÃ§ar na direÃ§Ã£o atual
  let target-patch patch-ahead move-dist
  ifelse target-patch != nobody and can-move-to-patch? target-patch [
    fd move-dist
  ] [
    ;; Tenta Ã¢ngulos alternativos (desvio progressivo)
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
    ;; Se nÃ£o moveu: permanece parado (congestionamento / jamming)
  ]
end

;; Reporter: o patch Ã© transitÃ¡vel?
to-report can-move-to-patch? [p]
  if p = nobody          [ report false ]
  if [is-wall?] of p    [ report false ]
  ;; Limite de densidade fÃ­sica: 6 ped/mÂ² (escala ajustada)
  let max-agents max list 1 floor (6.0 / population-scale)
  if count pedestrians-on p >= max-agents [ report false ]
  report true
end


;; ==========================================================
;; VERIFICAÃ‡ÃƒO DE CHEGADA Ã€ SAÃDA
;; ==========================================================
to check-exit-arrival   ;; turtle context
  if [is-exit?] of patch-here [
    set evacuated-count  evacuated-count  + population-scale
    set tick-evacuated   tick-evacuated   + population-scale
    die
  ]
end


;; ==========================================================
;; VISUALIZAÃ‡ÃƒO DOS PATCHES
;; ==========================================================
to update-patch-colors
  ask patches [
    ifelse is-wall? [
      set pcolor gray + 2
    ] [
      ifelse is-exit? [
        set pcolor green + 1
      ] [
        ifelse pedestrian-density > 0.5 [
          ;; Gradiente: azul (baixa) â†’ vermelho (alta)
          set pcolor scale-color red pedestrian-density 8 0
        ] [
          ifelse sector-id > 0 [
            set pcolor black + 1       ;; Piso do setor (escuro)
          ] [
            set pcolor black           ;; Ãrea externa
          ]
        ]
      ]
    ]
  ]
end


;; ==========================================================
;; REPORTERS PARA MONITORES DE INTERFACE
;; ==========================================================
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
824
519
-1
-1
5.0
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
119
0
99
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
no Parque Vila Germânica (Oktoberfest de Blumenau, SC) sob um
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
noturno no Parque Vila Germânica.
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
