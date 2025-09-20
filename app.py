import streamlit as st
import random
import pandas as pd

# --- セッション状態の初期化 ---
if "match_history" not in st.session_state:
    st.session_state.match_history = []
if "last_played_players" not in st.session_state:
    st.session_state.last_played_players = set()
if "round_count" not in st.session_state:
    st.session_state.round_count = 0
if "current_matches" not in st.session_state:
    st.session_state.current_matches = []
if "warning" not in st.session_state:
    st.session_state.warning = ""
if "player_match_count" not in st.session_state:
    st.session_state.player_match_count = {}
if "team_match_count" not in st.session_state:
    st.session_state.team_match_count = {}
if "manual_mode" not in st.session_state:
    st.session_state.manual_mode = False
if "show_force_confirm" not in st.session_state:
    st.session_state.show_force_confirm = False
if "selected_mode" not in st.session_state:
    st.session_state.selected_mode = "auto"

# --- 試合数バランス確認関数 ---
def get_match_balance_score(players, player_counts):
    """選手の試合数のバランススコアを計算（低いほど均衡している）"""
    if not players:
        return 0
    
    match_counts = []
    for player in players:
        total = player_counts.get(player, {}).get('シングルス', 0) + player_counts.get(player, {}).get('ダブルス', 0)
        match_counts.append(total)
    
    if not match_counts:
        return 0
    
    # 最大値と最小値の差をスコアとする
    return max(match_counts) - min(match_counts)

# --- 組み合わせ生成関数（段階的制約緩和対応） ---
def generate_matches_core(match_type, a_pool, b_pool, history, last_played, a_doubles_map, b_doubles_map, player_counts, max_rank_diff, allow_consecutive=False, allow_repeat_history=False, excluded_pairs=None):
    possible_matches = []
    excluded_pairs = excluded_pairs or set()
    
    if match_type == "シングルス":
        a_pool_dict = {player: [player] for player in a_pool}
        b_pool_dict = {player: [player] for player in b_pool}
    else:
        a_pool_dict = a_doubles_map
        b_pool_dict = b_doubles_map

    def sort_key(item_key, pool_dict, player_counts):
        players = pool_dict.get(item_key, [])
        total_matches = sum(player_counts.get(p, {}).get('シングルス', 0) + player_counts.get(p, {}).get('ダブルス', 0) for p in players)
        is_rested = all(player not in last_played for player in players)
        
        # 連戦回避は絶対条件、その後試合数で厳格にソート
        # 連戦の選手がいる場合は大きなペナルティを与える
        if not is_rested:
            return (1000 + total_matches, True)  # 連戦は最後に回す
        
        # 連戦でない場合のみ試合数で優先順位を決定
        return (total_matches, False)

    # 全選手のリストを作成（試合数バランス計算用）
    all_players = []
    if match_type == "シングルス":
        all_players = a_pool + b_pool
    else:
        # ダブルスの場合、ペアに含まれる全選手を取得
        for players in a_doubles_map.values():
            all_players.extend(players)
        for players in b_doubles_map.values():
            all_players.extend(players)
        # 重複を除去
        all_players = list(set(all_players))
    
    # 可能な組み合わせを生成（連戦回避を厳格に適用）
    valid_matches = []
    
    for a_item_key in a_pool_dict.keys():
        a_item_players = a_pool_dict.get(a_item_key, [])
        # 連戦チェック（allow_consecutiveが False の場合のみ）
        if not allow_consecutive and any(player in last_played for player in a_item_players):
            continue
        # ペア除外チェック
        if a_item_key in excluded_pairs:
            continue

        for b_item_key in b_pool_dict.keys():
            b_item_players = b_pool_dict.get(b_item_key, [])
            # 連戦チェック（allow_consecutiveが False の場合のみ）
            if not allow_consecutive and any(player in last_played for player in b_item_players):
                continue
            # ペア除外チェック
            if b_item_key in excluded_pairs:
                continue
            
            if a_item_key == b_item_key:
                continue

            # 過去の対戦履歴チェック（allow_repeat_historyが False の場合のみ）
            if not allow_repeat_history and any(
                (m["Team A"] == a_item_key and m["Team B"] == b_item_key) or
                (m["Team A"] == b_item_key and m["Team B"] == a_item_key) 
                for m in history
            ):
                continue
            
            # ランキング差チェック（シングルスの場合）
            if match_type == "シングルス":
                a_rank = int(a_item_key.strip("A"))
                b_rank = int(b_item_key.strip("B"))
                if abs(a_rank - b_rank) > max_rank_diff:
                    continue
            
            # この組み合わせに関わる選手の試合数を計算
            match_players = a_item_players + b_item_players
            total_matches = sum(player_counts.get(p, {}).get('シングルス', 0) + player_counts.get(p, {}).get('ダブルス', 0) for p in match_players)
            
            # この組み合わせ後の全体バランススコアを計算
            temp_player_counts = {}
            for player, counts in player_counts.items():
                temp_player_counts[player] = counts.copy()
            
            for player in match_players:
                if player not in temp_player_counts:
                    temp_player_counts[player] = {'シングルス': 0, 'ダブルス': 0}
                temp_player_counts[player][match_type] += 1
            
            balance_score = get_match_balance_score(all_players, temp_player_counts)
            
            valid_matches.append({
                'match': (a_item_key, b_item_key),
                'total_matches': total_matches,
                'balance_score': balance_score,
                'players': match_players
            })
    
    # 試合数バランスと総試合数で優先順位を決定
    # 1. バランススコアが低い（均衡している）
    # 2. 総試合数が少ない
    valid_matches.sort(key=lambda x: (x['balance_score'], x['total_matches']))
    
    return [match_info['match'] for match_info in valid_matches]

# --- 段階的制約緩和ラッパー関数 ---
def generate_matches(match_type, a_pool, b_pool, history, last_played, a_doubles_map, b_doubles_map, player_counts, max_rank_diff, allow_consecutive_global=True, allow_repeat_global=False, excluded_pairs=None):
    """段階的制約緩和でマッチング生成を試行"""
    
    # レベル1: 厳格（連戦回避 + 履歴回避）
    matches = generate_matches_core(match_type, a_pool, b_pool, history, last_played, a_doubles_map, b_doubles_map, player_counts, max_rank_diff, allow_consecutive=False, allow_repeat_history=False, excluded_pairs=excluded_pairs)
    if matches:
        return matches, "strict"
    
    # レベル2: 連戦許可（ユーザー設定に従う）
    if allow_consecutive_global:
        matches = generate_matches_core(match_type, a_pool, b_pool, history, last_played, a_doubles_map, b_doubles_map, player_counts, max_rank_diff, allow_consecutive=True, allow_repeat_history=False, excluded_pairs=excluded_pairs)
        if matches:
            return matches, "allow_consecutive"
    
    # レベル3: 全制約緩和（ユーザー設定に従う）
    if allow_repeat_global:
        matches = generate_matches_core(match_type, a_pool, b_pool, history, last_played, a_doubles_map, b_doubles_map, player_counts, max_rank_diff, allow_consecutive=True, allow_repeat_history=True, excluded_pairs=excluded_pairs)
        if matches:
            return matches, "allow_all"
    
    # どの制約でもマッチングできない場合
    return [], "failed"

# --- 選手抽出ヘルパー関数 ---
def get_players_from_selection(team_selection, match_type, doubles_input_dict):
    """選択されたチーム/ペアから個別の選手を抽出"""
    if not team_selection:
        return []
    
    if match_type == "シングルス":
        return team_selection  # 直接選手名
    else:
        # ダブルスペアから選手を抽出
        players = []
        for pair_name in team_selection:
            players.extend(doubles_input_dict.get(pair_name, []))
        return players

# --- 試合確定と状態更新関数 ---
def confirm_and_update_matches(matches_to_confirm, doubles_input):
    st.session_state.round_count += 1
    st.session_state.current_matches = matches_to_confirm
    
    st.session_state.last_played_players = set()
    
    for match, _, match_type in matches_to_confirm:
        st.session_state.match_history.append({
            "Round": st.session_state.round_count, "Match Type": match_type,
            "Team A": match[0], "Team B": match[1]
        })
        players_in_match = []
        if match_type == "シングルス":
            players_in_match.extend([match[0], match[1]])
        else:
            players_in_match.extend(doubles_input.get(match[0], []) + doubles_input.get(match[1], []))

        for player in players_in_match:
            st.session_state.last_played_players.add(player)
            st.session_state.player_match_count.setdefault(player, {"シングルス": 0, "ダブルス": 0})[match_type] += 1
        if match_type == "ダブルス":
            st.session_state.team_match_count.setdefault(match[0], 0)
            st.session_state.team_match_count[match[0]] += 1
            st.session_state.team_match_count.setdefault(match[1], 0)
            st.session_state.team_match_count[match[1]] += 1
    
    st.session_state.warning = ""
    st.session_state.manual_mode = False
    st.session_state.show_force_confirm = False
    st.rerun()

# --- Streamlit UI ---
st.title("テニス練習試合 組み合わせ生成アプリ")

# 選手数とランキング差の入力
st.header("参加人数とランキング設定")
col1, col2 = st.columns(2)
with col1:
    a_players_count = st.number_input("Aチームの選手数", min_value=0, value=8, key="a_players_count")
    a_doubles_count = st.number_input("Aチームのダブルスペア数", min_value=0, value=3, key="a_doubles_count")
with col2:
    b_players_count = st.number_input("Bチームの選手数", min_value=0, value=8, key="b_players_count")
    b_doubles_count = st.number_input("Bチームのダブルスペア数", min_value=0, value=3, key="b_doubles_count")

st.session_state.max_rank_diff = st.number_input("シングルスの最大ランキング差", min_value=1, value=3)

# 高度な設定
with st.expander("⚙️ 高度な設定", expanded=False):
    st.write("マッチング困難時の制約緩和設定")
    allow_consecutive_setting = st.checkbox("全員が使用済みの場合、連戦を許可する", value=True, help="全てのペア/選手が前ラウンドで試合した場合、連戦を許可してマッチングを継続")
    allow_repeat_setting = st.checkbox("マッチング困難時、過去の対戦を再度許可する", value=False, help="他の制約でマッチングできない場合、過去に対戦した組み合わせを再び許可")

a_players_list = [f"A{i}" for i in range(1, a_players_count + 1)]
b_players_list = [f"B{i}" for i in range(1, b_players_count + 1)]

# ダブルス選択UI
a_doubles_input = {}
b_doubles_input = {}
with st.expander("ダブルスペアの選択", expanded=False):
    st.subheader("Aチーム")
    cols = st.columns(a_doubles_count if a_doubles_count > 0 else 1)
    for i in range(a_doubles_count):
        with cols[i]:
            team_a_pair = st.multiselect(f"ペア{i+1}", a_players_list, max_selections=2, key=f"a_pair{i+1}")
            if len(team_a_pair) == 2:
                a_doubles_input[f"Aペア{i+1}"] = team_a_pair
    
    st.subheader("Bチーム")
    cols = st.columns(b_doubles_count if b_doubles_count > 0 else 1)
    for i in range(b_doubles_count):
        with cols[i]:
            team_b_pair = st.multiselect(f"ペア{i+1}", b_players_list, max_selections=2, key=f"b_pair{i+1}")
            if len(team_b_pair) == 2:
                b_doubles_input[f"Bペア{i+1}"] = team_b_pair

# --- UI表示の切り替え ---
st.header("組み合わせ生成方法")
st.write("どちらの方法で試合の組み合わせを作成しますか？")

col1, col2 = st.columns(2)

with col1:
    with st.container():
        st.subheader("🤖 自動生成（推奨）")
        st.write("• 試合数のバランスを自動調整")
        st.write("• 連戦を自動回避")  
        st.write("• 過去の対戦履歴を考慮")
        auto_button = st.button("自動生成を選択", key="auto_mode", use_container_width=True)

with col2:
    with st.container():
        st.subheader("✋ 手動選択")
        st.write("• 自由に組み合わせを指定")
        st.write("• 特定の対戦を設定可能")
        st.write("• 完全なコントロール")
        manual_button = st.button("手動選択を選択", key="manual_mode_button", use_container_width=True)

# ボタンが押された時の状態更新
if auto_button:
    st.session_state.selected_mode = "auto"
    st.session_state.manual_mode = False
    st.rerun()

if manual_button:
    st.session_state.selected_mode = "manual"
    st.session_state.manual_mode = True
    st.rerun()

# 現在のモード表示
if st.session_state.selected_mode == "auto":
    st.info("🤖 現在：自動生成モード")
else:
    st.info("✋ 現在：手動選択モード")

if st.session_state.manual_mode:
    st.subheader("手動で組み合わせを生成")
    
    col1, col2 = st.columns(2)
    with col1:
        manual_court_a_type = st.radio("コート1形式", ["シングルス", "ダブルス"], key="manual_court_a_type")
        
        if manual_court_a_type == "シングルス":
            manual_a_team = st.multiselect("コート1 Aチーム", a_players_list, max_selections=1, key="manual_a_team")
            manual_b_team = st.multiselect("コート1 Bチーム", b_players_list, max_selections=1, key="manual_b_team")
        else:
            manual_a_team = st.multiselect("コート1 Aチーム", list(a_doubles_input.keys()), max_selections=1, key="manual_a_team")
            manual_b_team = st.multiselect("コート1 Bチーム", list(b_doubles_input.keys()), max_selections=1, key="manual_b_team")

    with col2:
        manual_court_b_type = st.radio("コート2形式", ["シングルス", "ダブルス"], key="manual_court_b_type")

        if manual_court_b_type == "シングルス":
            manual_c_team = st.multiselect("コート2 Aチーム", a_players_list, max_selections=1, key="manual_c_team")
            manual_d_team = st.multiselect("コート2 Bチーム", b_players_list, max_selections=1, key="manual_d_team")
        else:
            manual_c_team = st.multiselect("コート2 Aチーム", list(a_doubles_input.keys()), max_selections=1, key="manual_c_team")
            manual_d_team = st.multiselect("コート2 Bチーム", list(b_doubles_input.keys()), max_selections=1, key="manual_d_team")

    
    col1, col2 = st.columns(2)
    with col1:
        if st.button("手動組み合わせを確定"):
            matches_to_confirm = []
            a_players = []
            b_players = []

            if manual_court_a_type == "シングルス" and manual_a_team and manual_b_team:
                matches_to_confirm.append(((manual_a_team[0], manual_b_team[0]), "コート1", "シングルス"))
                a_players.extend(manual_a_team)
                b_players.extend(manual_b_team)
            elif manual_court_a_type == "ダブルス" and manual_a_team and manual_b_team:
                matches_to_confirm.append(((manual_a_team[0], manual_b_team[0]), "コート1", "ダブルス"))
                a_players.extend(a_doubles_input.get(manual_a_team[0], []))
                b_players.extend(b_doubles_input.get(manual_b_team[0], []))

            if manual_court_b_type == "シングルス" and manual_c_team and manual_d_team:
                matches_to_confirm.append(((manual_c_team[0], manual_d_team[0]), "コート2", "シングルス"))
                a_players.extend(manual_c_team)
                b_players.extend(manual_d_team)
            elif manual_court_b_type == "ダブルス" and manual_c_team and manual_d_team:
                matches_to_confirm.append(((manual_c_team[0], manual_d_team[0]), "コート2", "ダブルス"))
                a_players.extend(a_doubles_input.get(manual_c_team[0], []))
                b_players.extend(b_doubles_input.get(manual_d_team[0], []))

            # コート間での重複選手チェック
            court_a_players = []
            court_b_players = []
            
            # コート1の選手を抽出
            if manual_court_a_type == "シングルス" and manual_a_team and manual_b_team:
                court_a_players.extend(manual_a_team + manual_b_team)
            elif manual_court_a_type == "ダブルス" and manual_a_team and manual_b_team:
                court_a_players.extend(get_players_from_selection(manual_a_team, "ダブルス", a_doubles_input))
                court_a_players.extend(get_players_from_selection(manual_b_team, "ダブルス", b_doubles_input))
            
            # コート2の選手を抽出
            if manual_court_b_type == "シングルス" and manual_c_team and manual_d_team:
                court_b_players.extend(manual_c_team + manual_d_team)
            elif manual_court_b_type == "ダブルス" and manual_c_team and manual_d_team:
                court_b_players.extend(get_players_from_selection(manual_c_team, "ダブルス", a_doubles_input))
                court_b_players.extend(get_players_from_selection(manual_d_team, "ダブルス", b_doubles_input))
            
            # 重複選手チェック
            duplicate_players = list(set(court_a_players) & set(court_b_players))
            
            if duplicate_players:
                st.error(f"同じ選手が複数のコートに選択されています: {', '.join(duplicate_players)}")
            else:
                all_selected_players = set(a_players + b_players)
                conflicting_players = list(all_selected_players.intersection(st.session_state.last_played_players))
                if conflicting_players:
                    st.warning(f"以下の選手が前回のラウンドでも試合に参加しています: {', '.join(conflicting_players)}")
                    st.session_state.show_force_confirm = True
                elif matches_to_confirm:
                    confirm_and_update_matches(matches_to_confirm, {**a_doubles_input, **b_doubles_input})
                else:
                    st.error("入力が不完全です。すべてのコートの選手と試合形式を設定してください。")

    with col2:
        if st.session_state.show_force_confirm:
            if st.button("強制的に確定", key="force_confirm_btn"):
                matches_to_confirm = []
                
                if manual_court_a_type == "シングルス" and manual_a_team and manual_b_team:
                    matches_to_confirm.append(((manual_a_team[0], manual_b_team[0]), "コート1", "シングルス"))
                elif manual_court_a_type == "ダブルス" and manual_a_team and manual_b_team:
                    matches_to_confirm.append(((manual_a_team[0], manual_b_team[0]), "コート1", "ダブルス"))

                if manual_court_b_type == "シングルス" and manual_c_team and manual_d_team:
                    matches_to_confirm.append(((manual_c_team[0], manual_d_team[0]), "コート2", "シングルス"))
                elif manual_court_b_type == "ダブルス" and manual_c_team and manual_d_team:
                    matches_to_confirm.append(((manual_c_team[0], manual_d_team[0]), "コート2", "ダブルス"))

                if matches_to_confirm:
                    confirm_and_update_matches(matches_to_confirm, {**a_doubles_input, **b_doubles_input})
                else:
                    st.error("入力が不完全です。すべてのコートの選手と試合形式を設定してください。")

    if st.button("自動生成モードに戻る", key="return_auto_mode"):
        st.session_state.selected_mode = "auto"
        st.session_state.manual_mode = False
        st.rerun()

# --- 自動生成モード ---
else:
    col1, col2 = st.columns(2)
    with col1:
        court_a_type = st.selectbox("コート1", ["シングルス", "ダブルス"], key='court_a_type')
    with col2:
        court_b_type = st.selectbox("コート2", ["シングルス", "ダブルス"], key='court_b_type')

    if st.button("次のラウンドの組み合わせを生成"):
        st.session_state.warning = ""
        st.session_state.last_generated_matches = []
        
        matches_a, constraint_level_a = generate_matches(court_a_type, a_players_list, b_players_list, st.session_state.match_history, st.session_state.last_played_players, a_doubles_input, b_doubles_input, st.session_state.player_match_count, st.session_state.max_rank_diff, allow_consecutive_setting, allow_repeat_setting)
        
        if matches_a:
            match_a = matches_a[0]
            
            # 制約緩和情報を表示
            if constraint_level_a == "allow_consecutive":
                st.warning("⚠️ コート1: 連戦を許可してマッチングしました")
            elif constraint_level_a == "allow_all":
                st.warning("⚠️ コート1: 連戦と過去の対戦を許可してマッチングしました")
            st.session_state.last_generated_matches.append((match_a, "コート1", court_a_type))
            
            # 使用済みペア情報を収集
            used_pairs = set()
            if court_a_type == "ダブルス":
                used_pairs.add(match_a[0])  # Aチームペア
                used_pairs.add(match_a[1])  # Bチームペア
            
            # プレイヤー情報も収集
            players_in_match_a = [match_a[0], match_a[1]] if court_a_type == "シングルス" else a_doubles_input.get(match_a[0], []) + b_doubles_input.get(match_a[1], [])
            last_played_for_b = set(players_in_match_a)
            combined_last_played = st.session_state.last_played_players | last_played_for_b

            # コート2生成（ペア除外も追加）
            matches_b, constraint_level_b = generate_matches(court_b_type, a_players_list, b_players_list, st.session_state.match_history, combined_last_played, a_doubles_input, b_doubles_input, st.session_state.player_match_count, st.session_state.max_rank_diff, allow_consecutive_setting, allow_repeat_setting, used_pairs)
            
            if matches_b:
                match_b = matches_b[0]
                
                # 制約緩和情報を表示
                if constraint_level_b == "allow_consecutive":
                    st.warning("⚠️ コート2: 連戦を許可してマッチングしました")
                elif constraint_level_b == "allow_all":
                    st.warning("⚠️ コート2: 連戦と過去の対戦を許可してマッチングしました")
                st.session_state.last_generated_matches.append((match_b, "コート2", court_b_type))
                confirm_and_update_matches(st.session_state.last_generated_matches, {**a_doubles_input, **b_doubles_input})
            elif constraint_level_b == "failed":
                if not allow_consecutive_setting:
                    st.session_state.warning = "コート2のマッチングに失敗しました。高度な設定で「連戦を許可」を有効にするか、手動で組み合わせてください。"
                else:
                    st.session_state.warning = "コート2のマッチングに失敗しました。手動で組み合わせを設定してください。"
            else:
                st.session_state.warning = "コート2のマッチングに問題がありました。下記の解決策を選んでください。"
        elif constraint_level_a == "failed":
            if not allow_consecutive_setting:
                st.session_state.warning = "コート1のマッチングに失敗しました。高度な設定で「連戦を許可」を有効にするか、手動で組み合わせてください。"
            else:
                st.session_state.warning = "コート1のマッチングに失敗しました。手動で組み合わせを設定してください。"
        else:
            st.session_state.warning = "コート1のマッチングに問題がありました。下記の解決策を選んでください。"

    if st.session_state.warning:
        st.warning(st.session_state.warning)
        st.subheader("解決策を選んでください:")
        col1, col2 = st.columns(2)
        with col1:
            if st.button("手動で組み合わせる"):
                st.session_state.selected_mode = "manual"
                st.session_state.manual_mode = True
                st.rerun()
        with col2:
            if st.button("試合形式を変えて再生成"):
                st.session_state.warning = ""
                st.session_state.last_generated_matches = []
                st.rerun()
    elif st.session_state.current_matches:
        st.header(f"第{st.session_state.round_count}ラウンド")
        for match, court, match_type in st.session_state.current_matches:
            st.write(f"**{court} ({match_type})**: {match[0]} vs {match[1]}")
    else:
        st.warning("「次のラウンドの組み合わせを生成」ボタンを押してください。")

st.write("---")

### 対戦履歴
st.subheader("対戦履歴")
history_df = pd.DataFrame(st.session_state.match_history)
if not history_df.empty:
    st.dataframe(history_df.set_index('Round'))
else:
    st.write("まだ対戦履歴はありません。")

st.write("---")

### 個人別試合数
st.subheader("個人別試合数")

# 全選手リストを生成（現在の設定に基づく）
all_players = [f"A{i}" for i in range(1, a_players_count + 1)] + [f"B{i}" for i in range(1, b_players_count + 1)]

# 全選手のデータを作成（未試合選手も含む）
match_data = []
for player in all_players:
    if player in st.session_state.player_match_count:
        counts = st.session_state.player_match_count[player]
        singles_count = counts['シングルス']
        doubles_count = counts['ダブルス']
    else:
        singles_count = 0
        doubles_count = 0
    
    total = singles_count + doubles_count
    match_data.append({
        'Player': player,
        'シングルス': singles_count,
        'ダブルス': doubles_count,
        'Total': total
    })

match_count_df = pd.DataFrame(match_data)
st.dataframe(match_count_df.sort_values(by="Player").set_index("Player"))

st.write("---")

### ペア別試合数
st.subheader("ペア別試合数")
if st.session_state.team_match_count:
    team_data = []
    for team, count in st.session_state.team_match_count.items():
        team_data.append({
            'Team': team,
            'Matches Played': count
        })
    team_count_df = pd.DataFrame(team_data)
    st.dataframe(team_count_df.sort_values(by="Team").set_index("Team"))
else:
    st.write("まだダブルスの試合は行われていません。")