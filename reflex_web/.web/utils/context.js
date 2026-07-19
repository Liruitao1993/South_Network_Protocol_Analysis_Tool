import { createContext, useContext, useMemo, useReducer, useState, createElement, useEffect } from "react"
import { applyDelta, ReflexEvent, hydrateClientStorage, useEventLoop, refs } from "$/utils/state"
import { jsx } from "@emotion/react";

export const initialState = {"reflex___state____state": {"is_hydrated_rx_state_": false, "router_rx_state_": {"session": {"client_token": "", "client_ip": "", "session_id": ""}, "headers": {"host": "", "origin": "", "upgrade": "", "connection": "", "cookie": "", "pragma": "", "cache_control": "", "user_agent": "", "sec_websocket_version": "", "sec_websocket_key": "", "sec_websocket_extensions": "", "accept_encoding": "", "accept_language": "", "raw_headers": {}}, "page": {"host": "", "path": "", "raw_path": "", "full_path": "", "full_raw_path": "", "params": {}}, "url": {"scheme": "", "netloc": "", "origin": "://", "path": "", "query": "", "query_parameters": {}, "fragment": "", "href": ""}, "route_id": ""}}, "reflex___state____state.reflex___istate___shared____shared_state_base_internal": {}, "reflex___state____state.reflex___state____frontend_event_exception_state": {}, "reflex___state____state.reflex___state____on_load_internal_state": {}, "reflex___state____state.reflex___state____update_vars_internal_state": {}, "reflex___state____state.reflex_web___reflex_web____state": {"PROTOCOL_OPTIONS_rx_state_": [{"label": "南网协议 (Q/CSG1209021-2019)", "value": "0"}, {"label": "PLC RF协议 (万胜海外 V1_04)", "value": "1"}, {"label": "HDLC/国网DLMS (IEC 62056-46)", "value": "2"}, {"label": "DLMS-APDU(国网)", "value": "3"}, {"label": "DLMS Wrapper裸报文", "value": "4"}, {"label": "DLMS-APDU裸报文", "value": "5"}, {"label": "DLT645-2007 电表协议", "value": "6"}, {"label": "国网协议 (Q/GDW 10376.2-2024)", "value": "7"}, {"label": "698.45协议 (DL/T 698.45-2017)", "value": "8"}, {"label": "新一代载波协议 (通感一体化)", "value": "9"}, {"label": "国网新一代双模通信互联互通", "value": "10"}], "active_tab_rx_state_": "single", "afn_fn_options_rx_state_": [], "batch_detail_hex_rx_state_": "", "batch_detail_rows_rx_state_": [], "batch_input_rx_state_": "", "batch_results_rx_state_": [], "batch_selected_idx_rx_state_": -1, "csg_parse_level_rx_state_": "auto", "current_protocol_rx_state_": 0, "di_options_rx_state_": [], "diff_left_rx_state_": "", "diff_result_rx_state_": [], "diff_right_rx_state_": "", "dlt698_apdu_options_rx_state_": [], "dlt698_sub_options_rx_state_": [], "frame_hex_rx_state_": "", "gen_afn_fn_rx_state_": "", "gen_di_key_rx_state_": "", "gen_dir_rx_state_": 0, "gen_dlt698_apdu_rx_state_": "", "gen_dlt698_sub_rx_state_": "", "gen_dst_addr_rx_state_": "000000000000", "gen_fields_rx_state_": {}, "gen_preview_rx_state_": "", "gen_prm_rx_state_": 1, "gen_protocol_rx_state_": 0, "gen_result_rx_state_": "", "gen_seq_rx_state_": 0, "gen_src_addr_rx_state_": "000000000000", "is_loading_rx_state_": false, "lookup_query_rx_state_": "", "lookup_results_rx_state_": [], "lookup_type_rx_state_": "di", "message_rx_state_": "", "message_type_rx_state_": "info", "parse_result_rx_state_": [], "strip_head_rx_state_": 0, "strip_tail_rx_state_": 0, "verify_result_rx_state_": ""}}

export const defaultColorMode = "light"
export const ColorModeContext = createContext({
  colorMode: defaultColorMode,
  resolvedColorMode: defaultColorMode === "dark" ? "dark" : "light",
  toggleColorMode: () => {},
  setColorMode: () => {},
});
export const UploadFilesContext = createContext(null);
export const DispatchContext = createContext(null);
export const StateContexts = {reflex___state____state: createContext(null),reflex___state____state__reflex___istate___shared____shared_state_base_internal: createContext(null),reflex___state____state__reflex___state____frontend_event_exception_state: createContext(null),reflex___state____state__reflex___state____on_load_internal_state: createContext(null),reflex___state____state__reflex___state____update_vars_internal_state: createContext(null),reflex___state____state__reflex_web___reflex_web____state: createContext(null),};
export const EventLoopContext = createContext(null);
export const clientStorage = {"cookies": {}, "local_storage": {}, "session_storage": {}}


export const state_name = "reflex___state____state"

export const exception_state_name = "reflex___state____state.reflex___state____frontend_event_exception_state"

// These events are triggered on initial load and each page navigation.
export const onLoadInternalEvent = () => {
    const internal_events = [];

    // Get tracked cookie and local storage vars to send to the backend.
    const client_storage_vars = hydrateClientStorage(clientStorage);
    // But only send the vars if any are actually set in the browser.
    if (client_storage_vars && Object.keys(client_storage_vars).length !== 0) {
        internal_events.push(
            ReflexEvent(
                'reflex___state____state.reflex___state____update_vars_internal_state.update_vars_internal',
                {vars: client_storage_vars},
            ),
        );
    }

    // `on_load_internal` triggers the correct on_load event(s) for the current page.
    // If the page does not define any on_load event, this will just set `is_hydrated = true`.
    internal_events.push(ReflexEvent('reflex___state____state.reflex___state____on_load_internal_state.on_load_internal'));

    return internal_events;
}

// The following events are sent when the websocket connects or reconnects.
export const initialEvents = () => [
    ReflexEvent('reflex___state____state.hydrate'),
    ...onLoadInternalEvent()
]
    

export const isDevMode = true;

// Module-level event dispatchers populated by ``EventLoopProvider`` on each
// render. Components reach addEvents/connectErrors via this import instead of
// hoisting ``useContext(EventLoopContext)`` so JSX literals (e.g.
// ``ErrorBoundary.onError``) constructed in any JS scope can dispatch events
// without depending on lexical hook hoisting.
let _addEventsImpl = (events, args, event_actions) => {
  console.warn("addEvents called before EventLoopProvider mounted", events);
};
let _connectErrorsImpl = [];

export function addEvents(events, args, event_actions) {
  return _addEventsImpl(events, args, event_actions);
}

export function getConnectErrors() {
  return _connectErrorsImpl;
}

export function UploadFilesProvider({ children }) {
  const [filesById, setFilesById] = useState({})
  refs["__clear_selected_files"] = (id) => setFilesById(filesById => {
    const newFilesById = {...filesById}
    delete newFilesById[id]
    return newFilesById
  })
  return createElement(
    UploadFilesContext.Provider,
    { value: [filesById, setFilesById] },
    children
  );
}

export function ClientSide(component) {
  return ({ children, ...props }) => {
    const [Component, setComponent] = useState(null);
    useEffect(() => {
      async function load() {
        const comp = await component();
        setComponent(() => comp);
      }
      load();
    }, []);
    return Component ? jsx(Component, props, children) : null;
  };
}

export function EventLoopProvider({ children }) {
  const dispatch = useContext(DispatchContext)
  const [addEventsLocal, connectErrors] = useEventLoop(
    dispatch,
    initialEvents,
    clientStorage,
  )
  // Populate the module-level dispatchers so JSX literals constructed
  // outside the React-tree path (e.g. ``ErrorBoundary.onError``) can call
  // ``addEvents`` without needing the events hook hoisted in their scope.
  _addEventsImpl = addEventsLocal;
  _connectErrorsImpl = connectErrors;
  return createElement(
    EventLoopContext.Provider,
    { value: [addEventsLocal, connectErrors] },
    children
  );
}

export function StateProvider({ children }) {
  const [reflex___state____state, dispatch_reflex___state____state] = useReducer(applyDelta, initialState["reflex___state____state"])
const [reflex___state____state__reflex___istate___shared____shared_state_base_internal, dispatch_reflex___state____state__reflex___istate___shared____shared_state_base_internal] = useReducer(applyDelta, initialState["reflex___state____state.reflex___istate___shared____shared_state_base_internal"])
const [reflex___state____state__reflex___state____frontend_event_exception_state, dispatch_reflex___state____state__reflex___state____frontend_event_exception_state] = useReducer(applyDelta, initialState["reflex___state____state.reflex___state____frontend_event_exception_state"])
const [reflex___state____state__reflex___state____on_load_internal_state, dispatch_reflex___state____state__reflex___state____on_load_internal_state] = useReducer(applyDelta, initialState["reflex___state____state.reflex___state____on_load_internal_state"])
const [reflex___state____state__reflex___state____update_vars_internal_state, dispatch_reflex___state____state__reflex___state____update_vars_internal_state] = useReducer(applyDelta, initialState["reflex___state____state.reflex___state____update_vars_internal_state"])
const [reflex___state____state__reflex_web___reflex_web____state, dispatch_reflex___state____state__reflex_web___reflex_web____state] = useReducer(applyDelta, initialState["reflex___state____state.reflex_web___reflex_web____state"])
  const dispatchers = useMemo(() => {
    return {
      "reflex___state____state": dispatch_reflex___state____state,
"reflex___state____state.reflex___istate___shared____shared_state_base_internal": dispatch_reflex___state____state__reflex___istate___shared____shared_state_base_internal,
"reflex___state____state.reflex___state____frontend_event_exception_state": dispatch_reflex___state____state__reflex___state____frontend_event_exception_state,
"reflex___state____state.reflex___state____on_load_internal_state": dispatch_reflex___state____state__reflex___state____on_load_internal_state,
"reflex___state____state.reflex___state____update_vars_internal_state": dispatch_reflex___state____state__reflex___state____update_vars_internal_state,
"reflex___state____state.reflex_web___reflex_web____state": dispatch_reflex___state____state__reflex_web___reflex_web____state,
    }
  }, [])

  return (
    createElement(StateContexts.reflex___state____state,{value: reflex___state____state},
createElement(StateContexts.reflex___state____state__reflex___istate___shared____shared_state_base_internal,{value: reflex___state____state__reflex___istate___shared____shared_state_base_internal},
createElement(StateContexts.reflex___state____state__reflex___state____frontend_event_exception_state,{value: reflex___state____state__reflex___state____frontend_event_exception_state},
createElement(StateContexts.reflex___state____state__reflex___state____on_load_internal_state,{value: reflex___state____state__reflex___state____on_load_internal_state},
createElement(StateContexts.reflex___state____state__reflex___state____update_vars_internal_state,{value: reflex___state____state__reflex___state____update_vars_internal_state},
createElement(StateContexts.reflex___state____state__reflex_web___reflex_web____state,{value: reflex___state____state__reflex_web___reflex_web____state},
    createElement(DispatchContext, {value: dispatchers}, children)
    ))))))
  )
}