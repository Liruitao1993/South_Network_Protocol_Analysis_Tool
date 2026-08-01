
import {ReflexEvent,applyEventActions,isNotNullOrUndefined,isTrue,pyOr} from "$/utils/state"
import {StateContexts,addEvents} from "$/utils/context"
import {Fragment,memo,useCallback,useContext,useEffect} from "react"
import {jsx} from "@emotion/react"
import {Badge as RadixThemesBadge,Button as RadixThemesButton,Callout as RadixThemesCallout,Card as RadixThemesCard,Checkbox as RadixThemesCheckbox,Code as RadixThemesCode,Flex as RadixThemesFlex,Table as RadixThemesTable,Text as RadixThemesText,TextArea as RadixThemesTextArea,TextField as RadixThemesTextField} from "@radix-ui/themes"
import {DynamicIcon} from "lucide-react/dynamic.mjs"
import LucideInfo from "lucide-react/dist/esm/icons/info.mjs"
import DebounceInput from "react-debounce-input"








export const Select_select_81b9ceaa8158c4ac27231e67af025afa_ed2d5185 = memo(({children}) => {
    const on_change_858ab76e93e047a56a0606d30c3cbada = useCallback(((_e) => (addEvents([(ReflexEvent("reflex___state____state.reflex_web___reflex_web____state.set_protocol", ({ ["value"] : _e?.["target"]?.["value"] }), ({  })))], [_e], ({  })))), [addEvents, ReflexEvent])



    return(
        jsx("select",{className:"rounded-md border border-white/30 bg-white/10 px-3 py-2 text-sm text-white focus:border-white/50",css:({ ["width"] : "280px" }),defaultValue:"0",onChange:on_change_858ab76e93e047a56a0606d30c3cbada},children)
    )
});

export const Select_select_fc154dae8e3241bdf69051761f8cf5be_ed2d5185 = memo(({children}) => {
    const on_change_ec8c27a3d4a7d0517eaad98b32d6dcca = useCallback(((_e) => (addEvents([(ReflexEvent("reflex___state____state.reflex_web___reflex_web____state.set_csg_level", ({ ["value"] : _e?.["target"]?.["value"] }), ({  })))], [_e], ({  })))), [addEvents, ReflexEvent])



    return(
        jsx("select",{className:"rounded border border-gray-300 px-2 py-1 text-sm",defaultValue:"auto",onChange:on_change_ec8c27a3d4a7d0517eaad98b32d6dcca},children)
    )
});

export const Cond_comp_b84525437a6536fe93fc22f52d282ca8_ed2d5185 = memo(({children}) => {
    const reflex___state____state__reflex_web___reflex_web____state = useContext(StateContexts.reflex___state____state__reflex_web___reflex_web____state)



    return(
        ((reflex___state____state__reflex_web___reflex_web____state.current_protocol_rx_state_?.valueOf?.() === 9?.valueOf?.())?(children?.at?.(0)):(children?.at?.(1)))
    )
});

export const Select_select_cef81ec3a02b6540bdb5300f4d776351_ed2d5185 = memo(({children}) => {
    const on_change_caac2b12db7591abcfbed7536a8828cb = useCallback(((_e) => (addEvents([(ReflexEvent("reflex___state____state.reflex_web___reflex_web____state.set_gw_level", ({ ["value"] : _e?.["target"]?.["value"] }), ({  })))], [_e], ({  })))), [addEvents, ReflexEvent])



    return(
        jsx("select",{className:"rounded border border-gray-300 px-2 py-1 text-sm",defaultValue:"auto",onChange:on_change_caac2b12db7591abcfbed7536a8828cb},children)
    )
});

export const Cond_comp_9a5e7d3de201160b1532285a4d4ea087_ed2d5185 = memo(({children}) => {
    const reflex___state____state__reflex_web___reflex_web____state = useContext(StateContexts.reflex___state____state__reflex_web___reflex_web____state)



    return(
        ((reflex___state____state__reflex_web___reflex_web____state.current_protocol_rx_state_?.valueOf?.() === 10?.valueOf?.())?(children?.at?.(0)):(children?.at?.(1)))
    )
});

export const Textfieldroot_textfield__root_59a847579f7b93d434d7fa66c4832091_ed2d5185 = memo(({children}) => {
    const on_change_365e50a21ce17cb56e763f2018776b36 = useCallback(((_e) => (addEvents([(ReflexEvent("reflex___state____state.reflex_web___reflex_web____state.set_strip_head", ({ ["value"] : _e?.["target"]?.["value"] }), ({  })))], [_e], ({  })))), [addEvents, ReflexEvent])



    return(
        jsx(RadixThemesTextField.Root,{css:({ ["width"] : "70px" }),defaultValue:"0",onChange:on_change_365e50a21ce17cb56e763f2018776b36,size:"1",type:"number"},)
    )
});

export const Textfieldroot_textfield__root_c620f203b3ff27e1c0bb97103f3c9643_ed2d5185 = memo(({children}) => {
    const on_change_b26e863b7f3ccd0c5ec66961a15d7cd1 = useCallback(((_e) => (addEvents([(ReflexEvent("reflex___state____state.reflex_web___reflex_web____state.set_strip_tail", ({ ["value"] : _e?.["target"]?.["value"] }), ({  })))], [_e], ({  })))), [addEvents, ReflexEvent])



    return(
        jsx(RadixThemesTextField.Root,{css:({ ["width"] : "70px" }),defaultValue:"0",onChange:on_change_b26e863b7f3ccd0c5ec66961a15d7cd1,size:"1",type:"number"},)
    )
});

export const Cond_comp_96627b3fd23f87a4d8d4f9ce40174445_ed2d5185 = memo(({children}) => {
    const reflex___state____state__reflex_web___reflex_web____state = useContext(StateContexts.reflex___state____state__reflex_web___reflex_web____state)



    return(
        (pyOr((reflex___state____state__reflex_web___reflex_web____state.current_protocol_rx_state_?.valueOf?.() === 9?.valueOf?.()), () => ((reflex___state____state__reflex_web___reflex_web____state.current_protocol_rx_state_?.valueOf?.() === 10?.valueOf?.())))?(children?.at?.(0)):(children?.at?.(1)))
    )
});

export const Dynamicicon_dynamicicon_756a536060e5d8a52e7578035aaae7ba_ed2d5185 = memo(({children}) => {
    const reflex___state____state__reflex_web___reflex_web____state = useContext(StateContexts.reflex___state____state__reflex_web___reflex_web____state)



    return(
        jsx(DynamicIcon,{name:((reflex___state____state__reflex_web___reflex_web____state.message_type_rx_state_?.valueOf?.() === "success"?.valueOf?.()) ? "check_circle" : ((reflex___state____state__reflex_web___reflex_web____state.message_type_rx_state_?.valueOf?.() === "error"?.valueOf?.()) ? "x_circle" : ((reflex___state____state__reflex_web___reflex_web____state.message_type_rx_state_?.valueOf?.() === "warning"?.valueOf?.()) ? "alert_triangle" : "info"))).replaceAll("_", "-")},)
    )
});

export const Bare_comp_86f89166d5d575dd57b1c07b1b32bb54_ed2d5185 = memo(({children}) => {
    const reflex___state____state__reflex_web___reflex_web____state = useContext(StateContexts.reflex___state____state__reflex_web___reflex_web____state)



    return(
        reflex___state____state__reflex_web___reflex_web____state.message_rx_state_
    )
});

export const Calloutroot_callout__root_0f37d783043ae170e3e04e3d543f17ec_ed2d5185 = memo(({children}) => {
    const reflex___state____state__reflex_web___reflex_web____state = useContext(StateContexts.reflex___state____state__reflex_web___reflex_web____state)



    return(
        jsx(RadixThemesCallout.Root,{color:((reflex___state____state__reflex_web___reflex_web____state.message_type_rx_state_?.valueOf?.() === "success"?.valueOf?.()) ? "green" : ((reflex___state____state__reflex_web___reflex_web____state.message_type_rx_state_?.valueOf?.() === "error"?.valueOf?.()) ? "red" : ((reflex___state____state__reflex_web___reflex_web____state.message_type_rx_state_?.valueOf?.() === "warning"?.valueOf?.()) ? "amber" : "blue"))),css:({ ["icon"] : ((reflex___state____state__reflex_web___reflex_web____state.message_type_rx_state_?.valueOf?.() === "success"?.valueOf?.()) ? "check_circle" : ((reflex___state____state__reflex_web___reflex_web____state.message_type_rx_state_?.valueOf?.() === "error"?.valueOf?.()) ? "x_circle" : ((reflex___state____state__reflex_web___reflex_web____state.message_type_rx_state_?.valueOf?.() === "warning"?.valueOf?.()) ? "alert_triangle" : "info"))), ["width"] : "100%", ["marginBottom"] : "3" }),size:"1"},children)
    )
});

export const Cond_comp_ef981f94da5302ccee7f3ee3468e28f1_ed2d5185 = memo(({children}) => {
    const reflex___state____state__reflex_web___reflex_web____state = useContext(StateContexts.reflex___state____state__reflex_web___reflex_web____state)



    return(
        (!((reflex___state____state__reflex_web___reflex_web____state.message_rx_state_?.valueOf?.() === ""?.valueOf?.()))?(children?.at?.(0)):(children?.at?.(1)))
    )
});

export const Button_button_94eae6c05dd777b8888472c712ab27ab_ed2d5185 = memo(({children}) => {
    const on_click_d5a51cb26eab8afbdbfd2e8c23cef43b = useCallback(((_e) => (addEvents([(ReflexEvent("reflex___state____state.reflex_web___reflex_web____state.set_tab", ({ ["tab"] : "single" }), ({  })))], [_e], ({  })))), [addEvents, ReflexEvent])
const reflex___state____state__reflex_web___reflex_web____state = useContext(StateContexts.reflex___state____state__reflex_web___reflex_web____state)



    return(
        jsx(RadixThemesButton,{color:((reflex___state____state__reflex_web___reflex_web____state.active_tab_rx_state_?.valueOf?.() === "single"?.valueOf?.()) ? "blue" : "gray"),onClick:on_click_d5a51cb26eab8afbdbfd2e8c23cef43b,size:"2",variant:((reflex___state____state__reflex_web___reflex_web____state.active_tab_rx_state_?.valueOf?.() === "single"?.valueOf?.()) ? "solid" : "soft")},children)
    )
});

export const Button_button_f33db702cf712eeb97bd566e4b25d40c_ed2d5185 = memo(({children}) => {
    const on_click_a659d195f919adede666658ae5eae31e = useCallback(((_e) => (addEvents([(ReflexEvent("reflex___state____state.reflex_web___reflex_web____state.set_tab", ({ ["tab"] : "batch" }), ({  })))], [_e], ({  })))), [addEvents, ReflexEvent])
const reflex___state____state__reflex_web___reflex_web____state = useContext(StateContexts.reflex___state____state__reflex_web___reflex_web____state)



    return(
        jsx(RadixThemesButton,{color:((reflex___state____state__reflex_web___reflex_web____state.active_tab_rx_state_?.valueOf?.() === "batch"?.valueOf?.()) ? "blue" : "gray"),onClick:on_click_a659d195f919adede666658ae5eae31e,size:"2",variant:((reflex___state____state__reflex_web___reflex_web____state.active_tab_rx_state_?.valueOf?.() === "batch"?.valueOf?.()) ? "solid" : "soft")},children)
    )
});

export const Button_button_1e1da7d93a5946718b12940dfe338a94_ed2d5185 = memo(({children}) => {
    const on_click_7c8cfb00635024cad938fe6783011c9c = useCallback(((_e) => (addEvents([(ReflexEvent("reflex___state____state.reflex_web___reflex_web____state.set_tab", ({ ["tab"] : "frame" }), ({  })))], [_e], ({  })))), [addEvents, ReflexEvent])
const reflex___state____state__reflex_web___reflex_web____state = useContext(StateContexts.reflex___state____state__reflex_web___reflex_web____state)



    return(
        jsx(RadixThemesButton,{color:((reflex___state____state__reflex_web___reflex_web____state.active_tab_rx_state_?.valueOf?.() === "frame"?.valueOf?.()) ? "blue" : "gray"),onClick:on_click_7c8cfb00635024cad938fe6783011c9c,size:"2",variant:((reflex___state____state__reflex_web___reflex_web____state.active_tab_rx_state_?.valueOf?.() === "frame"?.valueOf?.()) ? "solid" : "soft")},children)
    )
});

export const Button_button_feaffab82facc398f27163c273a7fca2_ed2d5185 = memo(({children}) => {
    const on_click_109cab525494ae39698ed0423807d265 = useCallback(((_e) => (addEvents([(ReflexEvent("reflex___state____state.reflex_web___reflex_web____state.set_tab", ({ ["tab"] : "diff" }), ({  })))], [_e], ({  })))), [addEvents, ReflexEvent])
const reflex___state____state__reflex_web___reflex_web____state = useContext(StateContexts.reflex___state____state__reflex_web___reflex_web____state)



    return(
        jsx(RadixThemesButton,{color:((reflex___state____state__reflex_web___reflex_web____state.active_tab_rx_state_?.valueOf?.() === "diff"?.valueOf?.()) ? "blue" : "gray"),onClick:on_click_109cab525494ae39698ed0423807d265,size:"2",variant:((reflex___state____state__reflex_web___reflex_web____state.active_tab_rx_state_?.valueOf?.() === "diff"?.valueOf?.()) ? "solid" : "soft")},children)
    )
});

export const Button_button_4bec0815dc2f9bb7ceffbc93a9ddb233_ed2d5185 = memo(({children}) => {
    const on_click_c4b5ded259b7209e68179eadf1ce8d0c = useCallback(((_e) => (addEvents([(ReflexEvent("reflex___state____state.reflex_web___reflex_web____state.set_tab", ({ ["tab"] : "lookup" }), ({  })))], [_e], ({  })))), [addEvents, ReflexEvent])
const reflex___state____state__reflex_web___reflex_web____state = useContext(StateContexts.reflex___state____state__reflex_web___reflex_web____state)



    return(
        jsx(RadixThemesButton,{color:((reflex___state____state__reflex_web___reflex_web____state.active_tab_rx_state_?.valueOf?.() === "lookup"?.valueOf?.()) ? "blue" : "gray"),onClick:on_click_c4b5ded259b7209e68179eadf1ce8d0c,size:"2",variant:((reflex___state____state__reflex_web___reflex_web____state.active_tab_rx_state_?.valueOf?.() === "lookup"?.valueOf?.()) ? "solid" : "soft")},children)
    )
});

export const Debounceinput_debounceinput_924e615fa1b70802ce1c935ce11b3482_ed2d5185 = memo(({children}) => {
    const on_change_08aac20f047085cb11593f9c723b2aae = useCallback(((_e) => (addEvents([(ReflexEvent("reflex___state____state.reflex_web___reflex_web____state.set_frame_hex", ({ ["value"] : _e?.["target"]?.["value"] }), ({  })))], [_e], ({  })))), [addEvents, ReflexEvent])
const reflex___state____state__reflex_web___reflex_web____state = useContext(StateContexts.reflex___state____state__reflex_web___reflex_web____state)



    return(
        jsx(DebounceInput,{css:({ ["height"] : "80px", ["width"] : "100%", ["fontFamily"] : "monospace", ["--default-font-family"] : "monospace", ["fontSize"] : "13px" }),debounceTimeout:300,element:RadixThemesTextArea,onChange:on_change_08aac20f047085cb11593f9c723b2aae,placeholder:"\u8bf7\u8f93\u5165\u5341\u516d\u8fdb\u5236\u62a5\u6587\uff0c\u5982: 68 0E 00 00 00 00 01 00 01 E8 00 05 EF 16",value:reflex___state____state__reflex_web___reflex_web____state.frame_hex_rx_state_},)
    )
});

export const Cond_comp_3b647ab99115a16915a7f192f2be0c4d_ed2d5185 = memo(({children}) => {
    const reflex___state____state__reflex_web___reflex_web____state = useContext(StateContexts.reflex___state____state__reflex_web___reflex_web____state)



    return(
        (reflex___state____state__reflex_web___reflex_web____state.is_loading_rx_state_?(children?.at?.(0)):(children?.at?.(1)))
    )
});

export const Button_button_f67ec4e9561583d7605f67b3eb1d332d_ed2d5185 = memo(({children}) => {
    const on_click_55bdfc2bcd9411b9c45863da312d5174 = useCallback(((_e) => (addEvents([(ReflexEvent("reflex___state____state.reflex_web___reflex_web____state.parse_frame", ({  }), ({  })))], [_e], ({  })))), [addEvents, ReflexEvent])
const reflex___state____state__reflex_web___reflex_web____state = useContext(StateContexts.reflex___state____state__reflex_web___reflex_web____state)



    return(
        jsx(RadixThemesButton,{color:"blue",loading:reflex___state____state__reflex_web___reflex_web____state.is_loading_rx_state_,onClick:on_click_55bdfc2bcd9411b9c45863da312d5174,size:"2"},children)
    )
});

export const Button_button_e0ee48fe20171796bf8752eced39ecb4_ed2d5185 = memo(({children}) => {
    const on_click_be548cfd7e1a5d8009452ce89c646b06 = useCallback(((_e) => (addEvents([(ReflexEvent("reflex___state____state.reflex_web___reflex_web____state.verify_frame", ({  }), ({  })))], [_e], ({  })))), [addEvents, ReflexEvent])



    return(
        jsx(RadixThemesButton,{color:"cyan",onClick:on_click_be548cfd7e1a5d8009452ce89c646b06,size:"2",variant:"outline"},children)
    )
});

export const Button_button_4be85304cf48ff65b9706183990f308e_ed2d5185 = memo(({children}) => {
    const on_click_06eb087da9bc6bff9c916178a3e0c157 = useCallback(((_e) => (addEvents([(ReflexEvent("reflex___state____state.reflex_web___reflex_web____state.clear_input", ({  }), ({  })))], [_e], ({  })))), [addEvents, ReflexEvent])



    return(
        jsx(RadixThemesButton,{color:"gray",onClick:on_click_06eb087da9bc6bff9c916178a3e0c157,size:"2",variant:"outline"},children)
    )
});

export const Bare_comp_cc007f0bc2426f3c193617d8f2f3d929_ed2d5185 = memo(({children}) => {
    const reflex___state____state__reflex_web___reflex_web____state = useContext(StateContexts.reflex___state____state__reflex_web___reflex_web____state)



    return(
        (reflex___state____state__reflex_web___reflex_web____state.parse_result_rx_state_.length+" \u6761")
    )
});

export const Foreach_comp_49f83c338d67f06808e00511a2f2ac17_ed2d5185 = memo(({children}) => {
    const reflex___state____state__reflex_web___reflex_web____state = useContext(StateContexts.reflex___state____state__reflex_web___reflex_web____state)



    return(
        Array.prototype.map.call(reflex___state____state__reflex_web___reflex_web____state.parse_result_rx_state_ ?? [],((row_rx_state_,index_25271effe7a9acd44d6898b87f566530)=>(jsx(RadixThemesTable.Row,{key:index_25271effe7a9acd44d6898b87f566530},jsx(RadixThemesTable.Cell,{css:({ ["fontWeight"] : "medium" })},row_rx_state_?.["field"]),jsx(RadixThemesTable.Cell,{},jsx(RadixThemesCode,{variant:"soft"},row_rx_state_?.["raw"])),jsx(RadixThemesTable.Cell,{},row_rx_state_?.["parsed"]),jsx(RadixThemesTable.Cell,{},jsx(RadixThemesText,{as:"p",css:({ ["color"] : "gray" }),size:"1"},row_rx_state_?.["comment"]))))))
    )
});

export const Cond_comp_da67cfc10e3dec0159f69b27a87f1041_ed2d5185 = memo(({children}) => {
    const reflex___state____state__reflex_web___reflex_web____state = useContext(StateContexts.reflex___state____state__reflex_web___reflex_web____state)



    return(
        ((reflex___state____state__reflex_web___reflex_web____state.parse_result_rx_state_.length > 0)?(children?.at?.(0)):(children?.at?.(1)))
    )
});

export const Bare_comp_bf0c0530254fd08f8e19bf2f199c198e_ed2d5185 = memo(({children}) => {
    const reflex___state____state__reflex_web___reflex_web____state = useContext(StateContexts.reflex___state____state__reflex_web___reflex_web____state)



    return(
        reflex___state____state__reflex_web___reflex_web____state.verify_result_rx_state_
    )
});

export const Cond_comp_3af8df9777f5c69db25f4ab571e676ba_ed2d5185 = memo(({children}) => {
    const reflex___state____state__reflex_web___reflex_web____state = useContext(StateContexts.reflex___state____state__reflex_web___reflex_web____state)



    return(
        (!((reflex___state____state__reflex_web___reflex_web____state.verify_result_rx_state_?.valueOf?.() === ""?.valueOf?.()))?(children?.at?.(0)):(children?.at?.(1)))
    )
});

export const Debounceinput_debounceinput_a94ba7e2648e689a5911a4fd1ca7c381_ed2d5185 = memo(({children}) => {
    const on_change_88d4b09ba8f3fac133b6802699c06b71 = useCallback(((_e) => (addEvents([(ReflexEvent("reflex___state____state.reflex_web___reflex_web____state.set_batch_input", ({ ["value"] : _e?.["target"]?.["value"] }), ({  })))], [_e], ({  })))), [addEvents, ReflexEvent])
const reflex___state____state__reflex_web___reflex_web____state = useContext(StateContexts.reflex___state____state__reflex_web___reflex_web____state)



    return(
        jsx(DebounceInput,{css:({ ["height"] : "120px", ["width"] : "100%", ["fontFamily"] : "monospace", ["--default-font-family"] : "monospace", ["fontSize"] : "13px" }),debounceTimeout:300,element:RadixThemesTextArea,onChange:on_change_88d4b09ba8f3fac133b6802699c06b71,placeholder:"\u7c98\u8d34\u76d1\u63a7\u65e5\u5fd7\u6216\u5341\u516d\u8fdb\u5236\u62a5\u6587\uff0c\u6bcf\u884c\u4e00\u5e27",value:reflex___state____state__reflex_web___reflex_web____state.batch_input_rx_state_},)
    )
});

export const Button_button_1e8a0911c7339d424f273daaabbb73af_ed2d5185 = memo(({children}) => {
    const on_click_7bea17e93527b56bfbeea8780a6ef853 = useCallback(((_e) => (addEvents([(ReflexEvent("reflex___state____state.reflex_web___reflex_web____state.parse_batch", ({  }), ({  })))], [_e], ({  })))), [addEvents, ReflexEvent])
const reflex___state____state__reflex_web___reflex_web____state = useContext(StateContexts.reflex___state____state__reflex_web___reflex_web____state)



    return(
        jsx(RadixThemesButton,{color:"blue",loading:reflex___state____state__reflex_web___reflex_web____state.is_loading_rx_state_,onClick:on_click_7bea17e93527b56bfbeea8780a6ef853,size:"2"},children)
    )
});

export const Button_button_6531aae331fb5f0855ab862bbea47c91_ed2d5185 = memo(({children}) => {
    const on_click_3a522f7abbe8a279c5d6086292d6da7b = useCallback(((_e) => (addEvents([(ReflexEvent("reflex___state____state.reflex_web___reflex_web____state.clear_batch", ({  }), ({  })))], [_e], ({  })))), [addEvents, ReflexEvent])



    return(
        jsx(RadixThemesButton,{color:"gray",onClick:on_click_3a522f7abbe8a279c5d6086292d6da7b,size:"2",variant:"outline"},children)
    )
});

export const Bare_comp_82e8ef0ad81739e9b57a753376569749_ed2d5185 = memo(({children}) => {
    const reflex___state____state__reflex_web___reflex_web____state = useContext(StateContexts.reflex___state____state__reflex_web___reflex_web____state)



    return(
        ("\u5171 "+reflex___state____state__reflex_web___reflex_web____state.batch_results_rx_state_.length+" \u5e27")
    )
});

export const Foreach_comp_3bbb9ae5ff86594df1bf799414682ed3_ed2d5185 = memo(({children}) => {
    const reflex___state____state__reflex_web___reflex_web____state = useContext(StateContexts.reflex___state____state__reflex_web___reflex_web____state)



    return(
        Array.prototype.map.call(reflex___state____state__reflex_web___reflex_web____state.batch_results_rx_state_ ?? [],((item_rx_state_,idx_rx_state_)=>(jsx(RadixThemesCard,{css:({ ["&"] : ((reflex___state____state__reflex_web___reflex_web____state.batch_selected_idx_rx_state_?.valueOf?.() === item_rx_state_?.["id"]?.valueOf?.()) ? ({ ["border"] : "2px solid #2563eb" }) : ({  })), ["padding"] : "2", ["width"] : "100%", ["cursor"] : "pointer", ["&:hover"] : ({ ["background"] : "rgba(37, 99, 235, 0.05)" }) }),key:idx_rx_state_,onClick:((_e) => (addEvents([(ReflexEvent("reflex___state____state.reflex_web___reflex_web____state.select_batch_by_index", ({ ["index"] : idx_rx_state_ }), ({  })))], [_e], ({  }))))},jsx(RadixThemesFlex,{align:"center",className:"rx-Stack",direction:"row",gap:"2"},jsx(RadixThemesBadge,{color:((item_rx_state_?.["status"]?.valueOf?.() === "\u6210\u529f"?.valueOf?.()) ? "green" : ((item_rx_state_?.["status"]?.valueOf?.() === "\u5931\u8d25"?.valueOf?.()) ? "red" : "amber")),size:"1",variant:"soft"},item_rx_state_?.["status"]),jsx(RadixThemesText,{as:"p",css:({ ["fontWeight"] : "bold" }),size:"1"},("#"+(JSON.stringify((idx_rx_state_ + 1))))),jsx(RadixThemesText,{as:"p",css:({ ["color"] : "gray" }),size:"1"},((JSON.stringify(item_rx_state_?.["len"]))+"B")),jsx(RadixThemesText,{as:"p",css:({ ["fontWeight"] : "medium" }),size:"1"},item_rx_state_?.["proto"]),jsx(RadixThemesFlex,{css:({ ["flex"] : 1, ["justifySelf"] : "stretch", ["alignSelf"] : "stretch" })},)),jsx(RadixThemesText,{as:"p",css:({ ["color"] : "gray", ["noOfLines"] : 2 }),size:"1"},item_rx_state_?.["summary"])))))
    )
});

export const Cond_comp_be5adffab2de6d0d3acf597d4d936da6_ed2d5185 = memo(({children}) => {
    const reflex___state____state__reflex_web___reflex_web____state = useContext(StateContexts.reflex___state____state__reflex_web___reflex_web____state)



    return(
        ((reflex___state____state__reflex_web___reflex_web____state.batch_results_rx_state_.length > 0)?(children?.at?.(0)):(children?.at?.(1)))
    )
});

export const Bare_comp_d3cc60ef072ef52724fe70f5a6f620c8_ed2d5185 = memo(({children}) => {
    const reflex___state____state__reflex_web___reflex_web____state = useContext(StateContexts.reflex___state____state__reflex_web___reflex_web____state)



    return(
        reflex___state____state__reflex_web___reflex_web____state.batch_detail_hex_rx_state_
    )
});

export const Cond_comp_649d244813517936aa6dbe6207558443_ed2d5185 = memo(({children}) => {
    const reflex___state____state__reflex_web___reflex_web____state = useContext(StateContexts.reflex___state____state__reflex_web___reflex_web____state)



    return(
        (!((reflex___state____state__reflex_web___reflex_web____state.batch_detail_hex_rx_state_?.valueOf?.() === ""?.valueOf?.()))?(children?.at?.(0)):(children?.at?.(1)))
    )
});

export const Foreach_comp_fe2f45970f78c5e3b645fa9f2b184c31_ed2d5185 = memo(({children}) => {
    const reflex___state____state__reflex_web___reflex_web____state = useContext(StateContexts.reflex___state____state__reflex_web___reflex_web____state)



    return(
        Array.prototype.map.call(reflex___state____state__reflex_web___reflex_web____state.batch_detail_rows_rx_state_ ?? [],((row_rx_state_,index_9aa91d83e6956e2ef1130d720a2adbdf)=>(jsx(RadixThemesTable.Row,{key:index_9aa91d83e6956e2ef1130d720a2adbdf},jsx(RadixThemesTable.Cell,{css:({ ["fontWeight"] : "medium", ["size"] : "1" })},row_rx_state_?.["field"]),jsx(RadixThemesTable.Cell,{css:({ ["size"] : "1" })},jsx(RadixThemesCode,{variant:"soft"},row_rx_state_?.["raw"])),jsx(RadixThemesTable.Cell,{css:({ ["size"] : "1" })},row_rx_state_?.["parsed"]),jsx(RadixThemesTable.Cell,{},jsx(RadixThemesText,{as:"p",css:({ ["color"] : "gray" }),size:"1"},row_rx_state_?.["comment"]))))))
    )
});

export const Cond_comp_bf63dbcc8715775d6765d1f8c1ab8427_ed2d5185 = memo(({children}) => {
    const reflex___state____state__reflex_web___reflex_web____state = useContext(StateContexts.reflex___state____state__reflex_web___reflex_web____state)



    return(
        ((reflex___state____state__reflex_web___reflex_web____state.batch_detail_rows_rx_state_.length > 0)?(children?.at?.(0)):(children?.at?.(1)))
    )
});

export const Cond_comp_1b40066bd807f4bf697de19cf8a8e3e5_ed2d5185 = memo(({children}) => {
    const reflex___state____state__reflex_web___reflex_web____state = useContext(StateContexts.reflex___state____state__reflex_web___reflex_web____state)



    return(
        (pyOr(pyOr((reflex___state____state__reflex_web___reflex_web____state.current_protocol_rx_state_?.valueOf?.() === 0?.valueOf?.()), () => ((reflex___state____state__reflex_web___reflex_web____state.current_protocol_rx_state_?.valueOf?.() === 7?.valueOf?.()))), () => ((reflex___state____state__reflex_web___reflex_web____state.current_protocol_rx_state_?.valueOf?.() === 8?.valueOf?.())))?(children?.at?.(0)):(children?.at?.(1)))
    )
});

export const Foreach_comp_78ab9ce21c6181431923cff648565e7f_ed2d5185 = memo(({children}) => {
    const reflex___state____state__reflex_web___reflex_web____state = useContext(StateContexts.reflex___state____state__reflex_web___reflex_web____state)



    return(
        Array.prototype.map.call(reflex___state____state__reflex_web___reflex_web____state.di_options_rx_state_ ?? [],((opt_rx_state_,index_09b52d5f3a7764254e630e744628a8fd)=>(jsx("option",{key:index_09b52d5f3a7764254e630e744628a8fd,value:opt_rx_state_?.["value"]},opt_rx_state_?.["label"]))))
    )
});

export const Select_select_a1b273f233f66469fa25f4fec184fa20_ed2d5185 = memo(({children}) => {
    const on_change_ad6b92a80875d8b73bbd86f52f7ae7d1 = useCallback(((_e) => (addEvents([(ReflexEvent("reflex___state____state.reflex_web___reflex_web____state.set_gen_di_key", ({ ["value"] : _e?.["target"]?.["value"] }), ({  })))], [_e], ({  })))), [addEvents, ReflexEvent])



    return(
        jsx("select",{className:"flex-1 rounded border border-gray-300 px-3 py-2",defaultValue:"",onChange:on_change_ad6b92a80875d8b73bbd86f52f7ae7d1},children)
    )
});

export const Cond_comp_28f7fb89e3b852e35b6ead063a5dceb6_ed2d5185 = memo(({children}) => {
    const reflex___state____state__reflex_web___reflex_web____state = useContext(StateContexts.reflex___state____state__reflex_web___reflex_web____state)



    return(
        ((reflex___state____state__reflex_web___reflex_web____state.current_protocol_rx_state_?.valueOf?.() === 0?.valueOf?.())?(children?.at?.(0)):(children?.at?.(1)))
    )
});

export const Foreach_comp_75f059f99ab100ad4bb6c33689bf25d9_ed2d5185 = memo(({children}) => {
    const reflex___state____state__reflex_web___reflex_web____state = useContext(StateContexts.reflex___state____state__reflex_web___reflex_web____state)



    return(
        Array.prototype.map.call(reflex___state____state__reflex_web___reflex_web____state.afn_fn_options_rx_state_ ?? [],((opt_rx_state_,index_09b52d5f3a7764254e630e744628a8fd)=>(jsx("option",{key:index_09b52d5f3a7764254e630e744628a8fd,value:opt_rx_state_?.["value"]},opt_rx_state_?.["label"]))))
    )
});

export const Select_select_488b85862da47f23633a004e884dbfc0_ed2d5185 = memo(({children}) => {
    const on_change_816b40380c1b7004a47c443b3df7cf57 = useCallback(((_e) => (addEvents([(ReflexEvent("reflex___state____state.reflex_web___reflex_web____state.set_gen_afn_fn", ({ ["value"] : _e?.["target"]?.["value"] }), ({  })))], [_e], ({  })))), [addEvents, ReflexEvent])



    return(
        jsx("select",{className:"flex-1 rounded border border-gray-300 px-3 py-2",defaultValue:"",onChange:on_change_816b40380c1b7004a47c443b3df7cf57},children)
    )
});

export const Cond_comp_6f291f61131ab9ab5035bd5ceab30475_ed2d5185 = memo(({children}) => {
    const reflex___state____state__reflex_web___reflex_web____state = useContext(StateContexts.reflex___state____state__reflex_web___reflex_web____state)



    return(
        ((reflex___state____state__reflex_web___reflex_web____state.current_protocol_rx_state_?.valueOf?.() === 7?.valueOf?.())?(children?.at?.(0)):(children?.at?.(1)))
    )
});

export const Foreach_comp_64a87cb5abaf135ec8f7b0614304bfb7_ed2d5185 = memo(({children}) => {
    const reflex___state____state__reflex_web___reflex_web____state = useContext(StateContexts.reflex___state____state__reflex_web___reflex_web____state)



    return(
        Array.prototype.map.call(reflex___state____state__reflex_web___reflex_web____state.dlt698_apdu_options_rx_state_ ?? [],((opt_rx_state_,index_227c17b192003fea4a65b05ac462d949)=>(jsx("option",{key:index_227c17b192003fea4a65b05ac462d949,value:opt_rx_state_},opt_rx_state_))))
    )
});

export const Select_select_3bad275561d0ba7aae636d68b02937e7_ed2d5185 = memo(({children}) => {
    const on_change_155fc0233b3f354ed9fc7d2cbc02579b = useCallback(((_e) => (addEvents([(ReflexEvent("reflex___state____state.reflex_web___reflex_web____state.set_gen_dlt698_apdu", ({ ["value"] : _e?.["target"]?.["value"] }), ({  })))], [_e], ({  })))), [addEvents, ReflexEvent])



    return(
        jsx("select",{className:"flex-1 rounded border border-gray-300 px-3 py-2",defaultValue:"",onChange:on_change_155fc0233b3f354ed9fc7d2cbc02579b},children)
    )
});

export const Foreach_comp_3a9eec395a4d5040789243cfb8aeb82f_ed2d5185 = memo(({children}) => {
    const reflex___state____state__reflex_web___reflex_web____state = useContext(StateContexts.reflex___state____state__reflex_web___reflex_web____state)



    return(
        Array.prototype.map.call(reflex___state____state__reflex_web___reflex_web____state.dlt698_sub_options_rx_state_ ?? [],((opt_rx_state_,index_09b52d5f3a7764254e630e744628a8fd)=>(jsx("option",{key:index_09b52d5f3a7764254e630e744628a8fd,value:opt_rx_state_?.["value"]},opt_rx_state_?.["label"]))))
    )
});

export const Select_select_3d1c40eafaf7652c2e2e74742dc52039_ed2d5185 = memo(({children}) => {
    const on_change_4602200c24c7c15e8ee5c58b3152c3ed = useCallback(((_e) => (addEvents([(ReflexEvent("reflex___state____state.reflex_web___reflex_web____state.set_gen_dlt698_sub", ({ ["value"] : _e?.["target"]?.["value"] }), ({  })))], [_e], ({  })))), [addEvents, ReflexEvent])



    return(
        jsx("select",{className:"flex-1 rounded border border-gray-300 px-3 py-2",defaultValue:"",onChange:on_change_4602200c24c7c15e8ee5c58b3152c3ed},children)
    )
});

export const Cond_comp_e013ccd8fd2690d97d85354f5f58a215_ed2d5185 = memo(({children}) => {
    const reflex___state____state__reflex_web___reflex_web____state = useContext(StateContexts.reflex___state____state__reflex_web___reflex_web____state)



    return(
        (!((reflex___state____state__reflex_web___reflex_web____state.gen_dlt698_apdu_rx_state_?.valueOf?.() === ""?.valueOf?.()))?(children?.at?.(0)):(children?.at?.(1)))
    )
});

export const Cond_comp_a629efe019133eead87dedb9bb362528_ed2d5185 = memo(({children}) => {
    const reflex___state____state__reflex_web___reflex_web____state = useContext(StateContexts.reflex___state____state__reflex_web___reflex_web____state)



    return(
        ((reflex___state____state__reflex_web___reflex_web____state.current_protocol_rx_state_?.valueOf?.() === 8?.valueOf?.())?(children?.at?.(0)):(children?.at?.(1)))
    )
});

export const Debounceinput_debounceinput_f00fbc135108115c897a17c9f65c720d_ed2d5185 = memo(({children}) => {
    const on_change_ca77d4415aaac13b7b9bbb46de52ed81 = useCallback(((_e) => (addEvents([(ReflexEvent("reflex___state____state.reflex_web___reflex_web____state.set_gen_src_addr", ({ ["value"] : _e?.["target"]?.["value"] }), ({  })))], [_e], ({  })))), [addEvents, ReflexEvent])
const reflex___state____state__reflex_web___reflex_web____state = useContext(StateContexts.reflex___state____state__reflex_web___reflex_web____state)



    return(
        jsx(DebounceInput,{css:({ ["fontFamily"] : "monospace", ["--default-font-family"] : "monospace" }),debounceTimeout:300,element:RadixThemesTextField.Root,onChange:on_change_ca77d4415aaac13b7b9bbb46de52ed81,placeholder:"000000000000",size:"2",value:(isNotNullOrUndefined(reflex___state____state__reflex_web___reflex_web____state.gen_src_addr_rx_state_) ? reflex___state____state__reflex_web___reflex_web____state.gen_src_addr_rx_state_ : "")},)
    )
});

export const Debounceinput_debounceinput_ea65b964838d1d70d9d701e3fb0618ee_ed2d5185 = memo(({children}) => {
    const on_change_970a45b4e6001454789c2059d04bcdb2 = useCallback(((_e) => (addEvents([(ReflexEvent("reflex___state____state.reflex_web___reflex_web____state.set_gen_dst_addr", ({ ["value"] : _e?.["target"]?.["value"] }), ({  })))], [_e], ({  })))), [addEvents, ReflexEvent])
const reflex___state____state__reflex_web___reflex_web____state = useContext(StateContexts.reflex___state____state__reflex_web___reflex_web____state)



    return(
        jsx(DebounceInput,{css:({ ["fontFamily"] : "monospace", ["--default-font-family"] : "monospace" }),debounceTimeout:300,element:RadixThemesTextField.Root,onChange:on_change_970a45b4e6001454789c2059d04bcdb2,placeholder:"000000000000",size:"2",value:(isNotNullOrUndefined(reflex___state____state__reflex_web___reflex_web____state.gen_dst_addr_rx_state_) ? reflex___state____state__reflex_web___reflex_web____state.gen_dst_addr_rx_state_ : "")},)
    )
});

export const Debounceinput_debounceinput_8203fd9faaac6ad976c42166a0f4fc61_ed2d5185 = memo(({children}) => {
    const on_change_d9013e6eceb67f45a929478aab310ef3 = useCallback(((_e) => (addEvents([(ReflexEvent("reflex___state____state.reflex_web___reflex_web____state.set_gen_seq", ({ ["value"] : _e?.["target"]?.["value"] }), ({  })))], [_e], ({  })))), [addEvents, ReflexEvent])
const reflex___state____state__reflex_web___reflex_web____state = useContext(StateContexts.reflex___state____state__reflex_web___reflex_web____state)



    return(
        jsx(DebounceInput,{debounceTimeout:300,element:RadixThemesTextField.Root,onChange:on_change_d9013e6eceb67f45a929478aab310ef3,size:"2",type:"number",value:(isNotNullOrUndefined((JSON.stringify(reflex___state____state__reflex_web___reflex_web____state.gen_seq_rx_state_))) ? (JSON.stringify(reflex___state____state__reflex_web___reflex_web____state.gen_seq_rx_state_)) : "")},)
    )
});

export const Select_select_06ec504baecd643343823c705f7e5bc2_ed2d5185 = memo(({children}) => {
    const on_change_a253e073b5a192fe9da17a06cfed1d4a = useCallback(((_e) => (addEvents([(ReflexEvent("reflex___state____state.reflex_web___reflex_web____state.set_gen_dir", ({ ["value"] : _e?.["target"]?.["value"] }), ({  })))], [_e], ({  })))), [addEvents, ReflexEvent])



    return(
        jsx("select",{className:"rounded border border-gray-300 px-3 py-2",defaultValue:"0",onChange:on_change_a253e073b5a192fe9da17a06cfed1d4a},children)
    )
});

export const Select_select_6949ee9673aeb375bb0ef42a9d72462a_ed2d5185 = memo(({children}) => {
    const on_change_91e18e40a8c23f8e1e5bb1d293eb79f9 = useCallback(((_e) => (addEvents([(ReflexEvent("reflex___state____state.reflex_web___reflex_web____state.set_gen_prm", ({ ["value"] : _e?.["target"]?.["value"] }), ({  })))], [_e], ({  })))), [addEvents, ReflexEvent])



    return(
        jsx("select",{className:"rounded border border-gray-300 px-3 py-2",defaultValue:"1",onChange:on_change_91e18e40a8c23f8e1e5bb1d293eb79f9},children)
    )
});

export const Debounceinput_debounceinput_4d340e70fe46f3816f9e5762e1289213_ed2d5185 = memo(({children}) => {
    const on_change_0daea2ce74df5127b145e8f11c46ae6e = useCallback(((_e) => (addEvents([(ReflexEvent("reflex___state____state.reflex_web___reflex_web____state.set_gen_gdw_info", ({ ["key"] : "\u901a\u4fe1\u65b9\u5f0f", ["value"] : _e?.["target"]?.["value"] }), ({  })))], [_e], ({  })))), [addEvents, ReflexEvent])
const reflex___state____state__reflex_web___reflex_web____state = useContext(StateContexts.reflex___state____state__reflex_web___reflex_web____state)



    return(
        jsx(DebounceInput,{debounceTimeout:300,defaultValue:"3",element:RadixThemesTextField.Root,onChange:on_change_0daea2ce74df5127b145e8f11c46ae6e,size:"1",type:"number",value:(isNotNullOrUndefined(reflex___state____state__reflex_web___reflex_web____state.gen_gdw_info_rx_state_?.["\u901a\u4fe1\u65b9\u5f0f"]) ? reflex___state____state__reflex_web___reflex_web____state.gen_gdw_info_rx_state_?.["\u901a\u4fe1\u65b9\u5f0f"] : "")},)
    )
});

export const Debounceinput_debounceinput_466fd8fa9661a5670fd3f4efba2ee54c_ed2d5185 = memo(({children}) => {
    const on_change_ffb6ad0b2e1f91a0e698d694c32b8c95 = useCallback(((_e) => (addEvents([(ReflexEvent("reflex___state____state.reflex_web___reflex_web____state.set_gen_gdw_info", ({ ["key"] : "\u8def\u7531\u6807\u8bc6", ["value"] : _e?.["target"]?.["value"] }), ({  })))], [_e], ({  })))), [addEvents, ReflexEvent])
const reflex___state____state__reflex_web___reflex_web____state = useContext(StateContexts.reflex___state____state__reflex_web___reflex_web____state)



    return(
        jsx(DebounceInput,{debounceTimeout:300,defaultValue:"0",element:RadixThemesTextField.Root,onChange:on_change_ffb6ad0b2e1f91a0e698d694c32b8c95,size:"1",type:"number",value:(isNotNullOrUndefined(reflex___state____state__reflex_web___reflex_web____state.gen_gdw_info_rx_state_?.["\u8def\u7531\u6807\u8bc6"]) ? reflex___state____state__reflex_web___reflex_web____state.gen_gdw_info_rx_state_?.["\u8def\u7531\u6807\u8bc6"] : "")},)
    )
});

export const Debounceinput_debounceinput_092adf587429155ee4ab8eca59868e13_ed2d5185 = memo(({children}) => {
    const on_change_1efc4eafc925ef211d32e968d7fa0a1e = useCallback(((_e) => (addEvents([(ReflexEvent("reflex___state____state.reflex_web___reflex_web____state.set_gen_gdw_info", ({ ["key"] : "\u9644\u5c5e\u8282\u70b9\u6807\u8bc6", ["value"] : _e?.["target"]?.["value"] }), ({  })))], [_e], ({  })))), [addEvents, ReflexEvent])
const reflex___state____state__reflex_web___reflex_web____state = useContext(StateContexts.reflex___state____state__reflex_web___reflex_web____state)



    return(
        jsx(DebounceInput,{debounceTimeout:300,defaultValue:"0",element:RadixThemesTextField.Root,onChange:on_change_1efc4eafc925ef211d32e968d7fa0a1e,size:"1",type:"number",value:(isNotNullOrUndefined(reflex___state____state__reflex_web___reflex_web____state.gen_gdw_info_rx_state_?.["\u9644\u5c5e\u8282\u70b9\u6807\u8bc6"]) ? reflex___state____state__reflex_web___reflex_web____state.gen_gdw_info_rx_state_?.["\u9644\u5c5e\u8282\u70b9\u6807\u8bc6"] : "")},)
    )
});

export const Debounceinput_debounceinput_cb93dfc48df6ee9d595fef78820c4a91_ed2d5185 = memo(({children}) => {
    const on_change_865530fe889ae5e2841fc8d4603eb48b = useCallback(((_e) => (addEvents([(ReflexEvent("reflex___state____state.reflex_web___reflex_web____state.set_gen_gdw_info", ({ ["key"] : "\u901a\u4fe1\u6a21\u5757\u6807\u8bc6", ["value"] : _e?.["target"]?.["value"] }), ({  })))], [_e], ({  })))), [addEvents, ReflexEvent])
const reflex___state____state__reflex_web___reflex_web____state = useContext(StateContexts.reflex___state____state__reflex_web___reflex_web____state)



    return(
        jsx(DebounceInput,{debounceTimeout:300,defaultValue:"1",element:RadixThemesTextField.Root,onChange:on_change_865530fe889ae5e2841fc8d4603eb48b,size:"1",type:"number",value:(isNotNullOrUndefined(reflex___state____state__reflex_web___reflex_web____state.gen_gdw_info_rx_state_?.["\u901a\u4fe1\u6a21\u5757\u6807\u8bc6"]) ? reflex___state____state__reflex_web___reflex_web____state.gen_gdw_info_rx_state_?.["\u901a\u4fe1\u6a21\u5757\u6807\u8bc6"] : "")},)
    )
});

export const Debounceinput_debounceinput_05dd0435b477690d267b3634bf3b0ec9_ed2d5185 = memo(({children}) => {
    const on_change_ca21d187b056ca04bacb36b53f891724 = useCallback(((_e) => (addEvents([(ReflexEvent("reflex___state____state.reflex_web___reflex_web____state.set_gen_gdw_info", ({ ["key"] : "\u51b2\u7a81\u68c0\u6d4b", ["value"] : _e?.["target"]?.["value"] }), ({  })))], [_e], ({  })))), [addEvents, ReflexEvent])
const reflex___state____state__reflex_web___reflex_web____state = useContext(StateContexts.reflex___state____state__reflex_web___reflex_web____state)



    return(
        jsx(DebounceInput,{debounceTimeout:300,defaultValue:"0",element:RadixThemesTextField.Root,onChange:on_change_ca21d187b056ca04bacb36b53f891724,size:"1",type:"number",value:(isNotNullOrUndefined(reflex___state____state__reflex_web___reflex_web____state.gen_gdw_info_rx_state_?.["\u51b2\u7a81\u68c0\u6d4b"]) ? reflex___state____state__reflex_web___reflex_web____state.gen_gdw_info_rx_state_?.["\u51b2\u7a81\u68c0\u6d4b"] : "")},)
    )
});

export const Debounceinput_debounceinput_21dd95d01d8062d8db5b31d063b99b67_ed2d5185 = memo(({children}) => {
    const on_change_c9da53cd92b7b97ba4527b494ba4cb0a = useCallback(((_e) => (addEvents([(ReflexEvent("reflex___state____state.reflex_web___reflex_web____state.set_gen_gdw_info", ({ ["key"] : "\u4e2d\u7ee7\u7ea7\u522b", ["value"] : _e?.["target"]?.["value"] }), ({  })))], [_e], ({  })))), [addEvents, ReflexEvent])
const reflex___state____state__reflex_web___reflex_web____state = useContext(StateContexts.reflex___state____state__reflex_web___reflex_web____state)



    return(
        jsx(DebounceInput,{debounceTimeout:300,defaultValue:"0",element:RadixThemesTextField.Root,onChange:on_change_c9da53cd92b7b97ba4527b494ba4cb0a,size:"1",type:"number",value:(isNotNullOrUndefined(reflex___state____state__reflex_web___reflex_web____state.gen_gdw_info_rx_state_?.["\u4e2d\u7ee7\u7ea7\u522b"]) ? reflex___state____state__reflex_web___reflex_web____state.gen_gdw_info_rx_state_?.["\u4e2d\u7ee7\u7ea7\u522b"] : "")},)
    )
});

export const Debounceinput_debounceinput_d81c71b1ab9d1644545d75b22420131f_ed2d5185 = memo(({children}) => {
    const on_change_d7411be9acba4ad55ccc0dd0bf7a253d = useCallback(((_e) => (addEvents([(ReflexEvent("reflex___state____state.reflex_web___reflex_web____state.set_gen_gdw_info", ({ ["key"] : "\u7ea0\u9519\u7f16\u7801\u6807\u8bc6", ["value"] : _e?.["target"]?.["value"] }), ({  })))], [_e], ({  })))), [addEvents, ReflexEvent])
const reflex___state____state__reflex_web___reflex_web____state = useContext(StateContexts.reflex___state____state__reflex_web___reflex_web____state)



    return(
        jsx(DebounceInput,{debounceTimeout:300,defaultValue:"0",element:RadixThemesTextField.Root,onChange:on_change_d7411be9acba4ad55ccc0dd0bf7a253d,size:"1",type:"number",value:(isNotNullOrUndefined(reflex___state____state__reflex_web___reflex_web____state.gen_gdw_info_rx_state_?.["\u7ea0\u9519\u7f16\u7801\u6807\u8bc6"]) ? reflex___state____state__reflex_web___reflex_web____state.gen_gdw_info_rx_state_?.["\u7ea0\u9519\u7f16\u7801\u6807\u8bc6"] : "")},)
    )
});

export const Debounceinput_debounceinput_f547402e4bf4c90cc6ce7c6e94d406bc_ed2d5185 = memo(({children}) => {
    const on_change_9bc2a5e35e4f4d530a0fad8e5d4d48c0 = useCallback(((_e) => (addEvents([(ReflexEvent("reflex___state____state.reflex_web___reflex_web____state.set_gen_gdw_info", ({ ["key"] : "\u4fe1\u9053\u6807\u8bc6", ["value"] : _e?.["target"]?.["value"] }), ({  })))], [_e], ({  })))), [addEvents, ReflexEvent])
const reflex___state____state__reflex_web___reflex_web____state = useContext(StateContexts.reflex___state____state__reflex_web___reflex_web____state)



    return(
        jsx(DebounceInput,{debounceTimeout:300,defaultValue:"0",element:RadixThemesTextField.Root,onChange:on_change_9bc2a5e35e4f4d530a0fad8e5d4d48c0,size:"1",type:"number",value:(isNotNullOrUndefined(reflex___state____state__reflex_web___reflex_web____state.gen_gdw_info_rx_state_?.["\u4fe1\u9053\u6807\u8bc6"]) ? reflex___state____state__reflex_web___reflex_web____state.gen_gdw_info_rx_state_?.["\u4fe1\u9053\u6807\u8bc6"] : "")},)
    )
});

export const Debounceinput_debounceinput_d0ba794e76ab260907253e66f1831b0f_ed2d5185 = memo(({children}) => {
    const on_change_125157eb270126686c192d9772fe2370 = useCallback(((_e) => (addEvents([(ReflexEvent("reflex___state____state.reflex_web___reflex_web____state.set_gen_gdw_info", ({ ["key"] : "\u9884\u8ba1\u5e94\u7b54\u5b57\u8282\u6570", ["value"] : _e?.["target"]?.["value"] }), ({  })))], [_e], ({  })))), [addEvents, ReflexEvent])
const reflex___state____state__reflex_web___reflex_web____state = useContext(StateContexts.reflex___state____state__reflex_web___reflex_web____state)



    return(
        jsx(DebounceInput,{debounceTimeout:300,defaultValue:"0",element:RadixThemesTextField.Root,onChange:on_change_125157eb270126686c192d9772fe2370,size:"1",type:"number",value:(isNotNullOrUndefined(reflex___state____state__reflex_web___reflex_web____state.gen_gdw_info_rx_state_?.["\u9884\u8ba1\u5e94\u7b54\u5b57\u8282\u6570"]) ? reflex___state____state__reflex_web___reflex_web____state.gen_gdw_info_rx_state_?.["\u9884\u8ba1\u5e94\u7b54\u5b57\u8282\u6570"] : "")},)
    )
});

export const Debounceinput_debounceinput_8ae633ad8a3467c3ac5c2fd5f12dc9b5_ed2d5185 = memo(({children}) => {
    const on_change_b40dcb3abd4c652178760c631c932c91 = useCallback(((_e) => (addEvents([(ReflexEvent("reflex___state____state.reflex_web___reflex_web____state.set_gen_gdw_info", ({ ["key"] : "\u901a\u4fe1\u901f\u7387", ["value"] : _e?.["target"]?.["value"] }), ({  })))], [_e], ({  })))), [addEvents, ReflexEvent])
const reflex___state____state__reflex_web___reflex_web____state = useContext(StateContexts.reflex___state____state__reflex_web___reflex_web____state)



    return(
        jsx(DebounceInput,{debounceTimeout:300,defaultValue:"0",element:RadixThemesTextField.Root,onChange:on_change_b40dcb3abd4c652178760c631c932c91,size:"1",type:"number",value:(isNotNullOrUndefined(reflex___state____state__reflex_web___reflex_web____state.gen_gdw_info_rx_state_?.["\u901a\u4fe1\u901f\u7387"]) ? reflex___state____state__reflex_web___reflex_web____state.gen_gdw_info_rx_state_?.["\u901a\u4fe1\u901f\u7387"] : "")},)
    )
});

export const Debounceinput_debounceinput_5d4e7b8d5703ce03403a5fa6b84608f3_ed2d5185 = memo(({children}) => {
    const on_change_1fe347d3bd1ad06d3b25482b6380d2f2 = useCallback(((_e) => (addEvents([(ReflexEvent("reflex___state____state.reflex_web___reflex_web____state.set_gen_gdw_info", ({ ["key"] : "\u901f\u7387\u5355\u4f4d\u6807\u8bc6", ["value"] : _e?.["target"]?.["value"] }), ({  })))], [_e], ({  })))), [addEvents, ReflexEvent])
const reflex___state____state__reflex_web___reflex_web____state = useContext(StateContexts.reflex___state____state__reflex_web___reflex_web____state)



    return(
        jsx(DebounceInput,{debounceTimeout:300,defaultValue:"0",element:RadixThemesTextField.Root,onChange:on_change_1fe347d3bd1ad06d3b25482b6380d2f2,size:"1",type:"number",value:(isNotNullOrUndefined(reflex___state____state__reflex_web___reflex_web____state.gen_gdw_info_rx_state_?.["\u901f\u7387\u5355\u4f4d\u6807\u8bc6"]) ? reflex___state____state__reflex_web___reflex_web____state.gen_gdw_info_rx_state_?.["\u901f\u7387\u5355\u4f4d\u6807\u8bc6"] : "")},)
    )
});

export const Debounceinput_debounceinput_748de507d312e3d236cbb4a4b491934b_ed2d5185 = memo(({children}) => {
    const on_change_4a729260ce6c794f6737620f6d41f6d2 = useCallback(((_e) => (addEvents([(ReflexEvent("reflex___state____state.reflex_web___reflex_web____state.set_gen_gdw_info", ({ ["key"] : "\u62a5\u6587\u5e8f\u5217\u53f7", ["value"] : _e?.["target"]?.["value"] }), ({  })))], [_e], ({  })))), [addEvents, ReflexEvent])
const reflex___state____state__reflex_web___reflex_web____state = useContext(StateContexts.reflex___state____state__reflex_web___reflex_web____state)



    return(
        jsx(DebounceInput,{debounceTimeout:300,defaultValue:"0",element:RadixThemesTextField.Root,onChange:on_change_4a729260ce6c794f6737620f6d41f6d2,size:"1",type:"number",value:(isNotNullOrUndefined(reflex___state____state__reflex_web___reflex_web____state.gen_gdw_info_rx_state_?.["\u62a5\u6587\u5e8f\u5217\u53f7"]) ? reflex___state____state__reflex_web___reflex_web____state.gen_gdw_info_rx_state_?.["\u62a5\u6587\u5e8f\u5217\u53f7"] : "")},)
    )
});

export const Foreach_comp_8319e64941c97bb19d8818fb0f7180ed_ed2d5185 = memo(({children}) => {
    const reflex___state____state__reflex_web___reflex_web____state = useContext(StateContexts.reflex___state____state__reflex_web___reflex_web____state)



    return(
        Array.prototype.map.call(reflex___state____state__reflex_web___reflex_web____state.gen_field_schema_rx_state_ ?? [],((f_rx_state_,index_c66399894e577f389c8f45baaba19b1c)=>(jsx(RadixThemesFlex,{align:"start",className:"rx-Stack",direction:"column",key:index_c66399894e577f389c8f45baaba19b1c,gap:"1"},jsx(RadixThemesFlex,{align:"start",className:"rx-Stack",direction:"row",gap:"1"},jsx(RadixThemesText,{as:"p",css:({ ["fontWeight"] : "medium" }),size:"1"},f_rx_state_?.["name"]),jsx(RadixThemesBadge,{color:"gray",size:"1",variant:"soft"},f_rx_state_?.["type"])),jsx(DebounceInput,{css:({ ["fontFamily"] : "monospace", ["--default-font-family"] : "monospace" }),debounceTimeout:300,element:RadixThemesTextField.Root,onChange:((_e) => (addEvents([(ReflexEvent("reflex___state____state.reflex_web___reflex_web____state.set_gen_field", ({ ["key"] : f_rx_state_?.["name"], ["value"] : _e?.["target"]?.["value"] }), ({  })))], [_e], ({  })))),placeholder:f_rx_state_?.["default"],size:"1",value:(isNotNullOrUndefined(reflex___state____state__reflex_web___reflex_web____state.gen_fields_rx_state_?.[f_rx_state_?.["name"]]) ? reflex___state____state__reflex_web___reflex_web____state.gen_fields_rx_state_?.[f_rx_state_?.["name"]] : "")},),jsx(RadixThemesText,{as:"p",css:({ ["color"] : "gray" }),size:"1"},f_rx_state_?.["desc"])))))
    )
});

export const Cond_comp_fe097cbb3b98cf36101d6b8c798c1989_ed2d5185 = memo(({children}) => {
    const reflex___state____state__reflex_web___reflex_web____state = useContext(StateContexts.reflex___state____state__reflex_web___reflex_web____state)



    return(
        ((reflex___state____state__reflex_web___reflex_web____state.gen_field_schema_rx_state_.length > 0)?(children?.at?.(0)):(children?.at?.(1)))
    )
});

export const Bare_comp_98cfaad4390638ae37e884fa283bd1a4_ed2d5185 = memo(({children}) => {
    const reflex___state____state__reflex_web___reflex_web____state = useContext(StateContexts.reflex___state____state__reflex_web___reflex_web____state)



    return(
        reflex___state____state__reflex_web___reflex_web____state.gen_preview_rx_state_
    )
});

export const Bare_comp_fcaa07c1b26cde8a773fb1f9865cc50e_ed2d5185 = memo(({children}) => {
    const reflex___state____state__reflex_web___reflex_web____state = useContext(StateContexts.reflex___state____state__reflex_web___reflex_web____state)



    return(
        reflex___state____state__reflex_web___reflex_web____state.gen_result_rx_state_
    )
});

export const Cond_comp_c85874a80a8c210da0243b51ca4ca7cb_ed2d5185 = memo(({children}) => {
    const reflex___state____state__reflex_web___reflex_web____state = useContext(StateContexts.reflex___state____state__reflex_web___reflex_web____state)



    return(
        (!((reflex___state____state__reflex_web___reflex_web____state.gen_result_rx_state_?.valueOf?.() === ""?.valueOf?.()))?(children?.at?.(0)):(children?.at?.(1)))
    )
});

export const Button_button_e771cbcf60db0270539da0b4d5c77988_ed2d5185 = memo(({children}) => {
    const on_click_5121a49568644426c658ad8bf07e3c3a = useCallback(((_e) => (addEvents([(ReflexEvent("reflex___state____state.reflex_web___reflex_web____state.generate_frame", ({  }), ({  })))], [_e], ({  })))), [addEvents, ReflexEvent])
const reflex___state____state__reflex_web___reflex_web____state = useContext(StateContexts.reflex___state____state__reflex_web___reflex_web____state)



    return(
        jsx(RadixThemesButton,{color:"blue",loading:reflex___state____state__reflex_web___reflex_web____state.is_loading_rx_state_,onClick:on_click_5121a49568644426c658ad8bf07e3c3a,size:"2"},children)
    )
});

export const Button_button_af545c6220e27af60ae44ecd934047dc_ed2d5185 = memo(({children}) => {
    const on_click_275e3d44b522961b4c388c93da47d34d = useCallback(((_e) => (addEvents([(ReflexEvent("reflex___state____state.reflex_web___reflex_web____state.copy_gen_result", ({  }), ({  })))], [_e], ({  })))), [addEvents, ReflexEvent])
const reflex___state____state__reflex_web___reflex_web____state = useContext(StateContexts.reflex___state____state__reflex_web___reflex_web____state)



    return(
        jsx(RadixThemesButton,{color:"gray",disabled:(reflex___state____state__reflex_web___reflex_web____state.gen_result_hex_rx_state_?.valueOf?.() === ""?.valueOf?.()),onClick:on_click_275e3d44b522961b4c388c93da47d34d,size:"2",variant:"outline"},children)
    )
});

export const Debounceinput_debounceinput_f500b91b6dc33ef1f92884030b658be9_ed2d5185 = memo(({children}) => {
    const on_change_80341d9a427bc1b6aab5325ff0f18383 = useCallback(((_e) => (addEvents([(ReflexEvent("reflex___state____state.reflex_web___reflex_web____state.set_diff_left", ({ ["value"] : _e?.["target"]?.["value"] }), ({  })))], [_e], ({  })))), [addEvents, ReflexEvent])
const reflex___state____state__reflex_web___reflex_web____state = useContext(StateContexts.reflex___state____state__reflex_web___reflex_web____state)



    return(
        jsx(DebounceInput,{css:({ ["height"] : "100px", ["width"] : "100%", ["fontFamily"] : "monospace", ["--default-font-family"] : "monospace", ["fontSize"] : "12px" }),debounceTimeout:300,element:RadixThemesTextArea,onChange:on_change_80341d9a427bc1b6aab5325ff0f18383,placeholder:"\u8f93\u5165\u7b2c\u4e00\u4e2a\u62a5\u6587...",value:reflex___state____state__reflex_web___reflex_web____state.diff_left_rx_state_},)
    )
});

export const Debounceinput_debounceinput_b3a91f7e2662273a90642467b20a3ff8_ed2d5185 = memo(({children}) => {
    const on_change_130cc002cea256f4aedf42bb5549c428 = useCallback(((_e) => (addEvents([(ReflexEvent("reflex___state____state.reflex_web___reflex_web____state.set_diff_right", ({ ["value"] : _e?.["target"]?.["value"] }), ({  })))], [_e], ({  })))), [addEvents, ReflexEvent])
const reflex___state____state__reflex_web___reflex_web____state = useContext(StateContexts.reflex___state____state__reflex_web___reflex_web____state)



    return(
        jsx(DebounceInput,{css:({ ["height"] : "100px", ["width"] : "100%", ["fontFamily"] : "monospace", ["--default-font-family"] : "monospace", ["fontSize"] : "12px" }),debounceTimeout:300,element:RadixThemesTextArea,onChange:on_change_130cc002cea256f4aedf42bb5549c428,placeholder:"\u8f93\u5165\u7b2c\u4e8c\u4e2a\u62a5\u6587...",value:reflex___state____state__reflex_web___reflex_web____state.diff_right_rx_state_},)
    )
});

export const Button_button_02cc7cc02782e8e7bbd691dfc6a3cf68_ed2d5185 = memo(({children}) => {
    const on_click_89ba445ec77b01d6bc740cfacb289296 = useCallback(((_e) => (addEvents([(ReflexEvent("reflex___state____state.reflex_web___reflex_web____state.compare_frames", ({  }), ({  })))], [_e], ({  })))), [addEvents, ReflexEvent])
const reflex___state____state__reflex_web___reflex_web____state = useContext(StateContexts.reflex___state____state__reflex_web___reflex_web____state)



    return(
        jsx(RadixThemesButton,{color:"blue",loading:reflex___state____state__reflex_web___reflex_web____state.is_loading_rx_state_,onClick:on_click_89ba445ec77b01d6bc740cfacb289296,size:"2"},children)
    )
});

export const Button_button_fe6a08c6a4a1c63ce788c1a14eec07de_ed2d5185 = memo(({children}) => {
    const on_click_7a7f136c405ea13f4295f3f3c6130ecd = useCallback(((_e) => (addEvents([(ReflexEvent("reflex___state____state.reflex_web___reflex_web____state.clear_diff", ({  }), ({  })))], [_e], ({  })))), [addEvents, ReflexEvent])



    return(
        jsx(RadixThemesButton,{color:"gray",onClick:on_click_7a7f136c405ea13f4295f3f3c6130ecd,size:"2",variant:"outline"},children)
    )
});

export const Checkbox_checkbox_e1e2eeb68c9f6dd86b9c771590489e17_ed2d5185 = memo(({children}) => {
    const on_change_22bc2801aa56c4cf7cfc1fe945bef27b = useCallback(((_ev_0) => (addEvents([(ReflexEvent("reflex___state____state.reflex_web___reflex_web____state.toggle_diff_ignore_checksum", ({ ["value"] : _ev_0 }), ({  })))], [_ev_0], ({  })))), [addEvents, ReflexEvent])
const reflex___state____state__reflex_web___reflex_web____state = useContext(StateContexts.reflex___state____state__reflex_web___reflex_web____state)



    return(
        jsx(RadixThemesCheckbox,{checked:reflex___state____state__reflex_web___reflex_web____state.diff_ignore_checksum_rx_state_,onCheckedChange:on_change_22bc2801aa56c4cf7cfc1fe945bef27b,size:"2"},)
    )
});

export const Checkbox_checkbox_1cb4387dc8a5127ca533d0c1c72bf736_ed2d5185 = memo(({children}) => {
    const on_change_236de0a611658f151b130be65bcdcb05 = useCallback(((_ev_0) => (addEvents([(ReflexEvent("reflex___state____state.reflex_web___reflex_web____state.toggle_diff_ignore_sequence", ({ ["value"] : _ev_0 }), ({  })))], [_ev_0], ({  })))), [addEvents, ReflexEvent])
const reflex___state____state__reflex_web___reflex_web____state = useContext(StateContexts.reflex___state____state__reflex_web___reflex_web____state)



    return(
        jsx(RadixThemesCheckbox,{checked:reflex___state____state__reflex_web___reflex_web____state.diff_ignore_sequence_rx_state_,onCheckedChange:on_change_236de0a611658f151b130be65bcdcb05,size:"2"},)
    )
});

export const Checkbox_checkbox_cd18b5210035635c4455e0f9fb112bc2_ed2d5185 = memo(({children}) => {
    const on_change_60916d8e2f2eafd4f34217af020c1988 = useCallback(((_ev_0) => (addEvents([(ReflexEvent("reflex___state____state.reflex_web___reflex_web____state.toggle_diff_only_diff", ({ ["value"] : _ev_0 }), ({  })))], [_ev_0], ({  })))), [addEvents, ReflexEvent])
const reflex___state____state__reflex_web___reflex_web____state = useContext(StateContexts.reflex___state____state__reflex_web___reflex_web____state)



    return(
        jsx(RadixThemesCheckbox,{checked:reflex___state____state__reflex_web___reflex_web____state.diff_only_diff_rx_state_,onCheckedChange:on_change_60916d8e2f2eafd4f34217af020c1988,size:"2"},)
    )
});

export const Foreach_comp_a1f113fa5514ce7903959bf65315dd80_ed2d5185 = memo(({children}) => {
    const reflex___state____state__reflex_web___reflex_web____state = useContext(StateContexts.reflex___state____state__reflex_web___reflex_web____state)



    return(
        Array.prototype.map.call(reflex___state____state__reflex_web___reflex_web____state.diff_explanations_rx_state_ ?? [],((exp_rx_state_,index_8c469fdef9a93721a7836e8f8e71bedd)=>(jsx(RadixThemesFlex,{align:"start",className:"rx-Stack",css:({ ["paddingInlineStart"] : "2", ["paddingInlineEnd"] : "2", ["paddingTop"] : "1", ["paddingBottom"] : "1", ["width"] : "100%", ["background"] : "rgba(245, 158, 11, 0.05)", ["borderLeft"] : "3px solid #f59e0b", ["borderRadius"] : "4px" }),direction:"row",key:index_8c469fdef9a93721a7836e8f8e71bedd,gap:"2"},jsx(LucideInfo,{css:({ ["color"] : "#f59e0b", ["flexShrink"] : "0" }),size:14},),jsx(RadixThemesText,{as:"p",size:"2"},exp_rx_state_)))))
    )
});

export const Cond_comp_fd8b2289bfd2e425690bc588ec1b399e_ed2d5185 = memo(({children}) => {
    const reflex___state____state__reflex_web___reflex_web____state = useContext(StateContexts.reflex___state____state__reflex_web___reflex_web____state)



    return(
        ((reflex___state____state__reflex_web___reflex_web____state.diff_explanations_rx_state_.length > 0)?(children?.at?.(0)):(children?.at?.(1)))
    )
});

export const Bare_comp_00fab867f5c6bc7411657e398d6bd479_ed2d5185 = memo(({children}) => {
    const reflex___state____state__reflex_web___reflex_web____state = useContext(StateContexts.reflex___state____state__reflex_web___reflex_web____state)



    return(
        (reflex___state____state__reflex_web___reflex_web____state.diff_field_rows_rx_state_.length+" \u4e2a\u5b57\u6bb5")
    )
});

export const Foreach_comp_c11f894fbe655102504b7228dbf35c99_ed2d5185 = memo(({children}) => {
    const reflex___state____state__reflex_web___reflex_web____state = useContext(StateContexts.reflex___state____state__reflex_web___reflex_web____state)



    return(
        Array.prototype.map.call(reflex___state____state__reflex_web___reflex_web____state.diff_field_rows_rx_state_ ?? [],((row_rx_state_,index_6a7f7f00416a8246c86edc929b26f561)=>(jsx(RadixThemesTable.Row,{css:({ ["&"] : (!((row_rx_state_?.["diff_type"]?.valueOf?.() === "\u76f8\u540c"?.valueOf?.())) ? ({ ["background"] : "rgba(220, 38, 38, 0.03)" }) : ({  })) }),key:index_6a7f7f00416a8246c86edc929b26f561},jsx(RadixThemesTable.Cell,{css:({ ["fontWeight"] : "medium" })},row_rx_state_?.["field_name"]),jsx(RadixThemesTable.Cell,{},jsx(RadixThemesCode,{variant:"soft"},row_rx_state_?.["offset_display"])),jsx(RadixThemesTable.Cell,{},jsx(RadixThemesCode,{variant:"soft"},row_rx_state_?.["length_display"])),jsx(RadixThemesTable.Cell,{css:({ ["fontSize"] : "11px" })},jsx(RadixThemesCode,{variant:"soft"},row_rx_state_?.["value_a"])),jsx(RadixThemesTable.Cell,{css:({ ["fontSize"] : "11px" })},jsx(RadixThemesCode,{variant:"soft"},row_rx_state_?.["value_b"])),jsx(RadixThemesTable.Cell,{},jsx(RadixThemesBadge,{color:((row_rx_state_?.["diff_type"]?.valueOf?.() === "\u76f8\u540c"?.valueOf?.()) ? "green" : ((row_rx_state_?.["diff_type"]?.valueOf?.() === "\u4fee\u6539"?.valueOf?.()) ? "red" : ((row_rx_state_?.["diff_type"]?.valueOf?.() === "A\u72ec\u6709"?.valueOf?.()) ? "gray" : "amber"))),size:"1",variant:"soft"},row_rx_state_?.["diff_type"]))))))
    )
});

export const Cond_comp_89cd3b518a1d5810df8a507055fd719d_ed2d5185 = memo(({children}) => {
    const reflex___state____state__reflex_web___reflex_web____state = useContext(StateContexts.reflex___state____state__reflex_web___reflex_web____state)



    return(
        ((reflex___state____state__reflex_web___reflex_web____state.diff_field_rows_rx_state_.length > 0)?(children?.at?.(0)):(children?.at?.(1)))
    )
});

export const Bare_comp_3f15e1b0783b7fa4c1d5da158f610b79_ed2d5185 = memo(({children}) => {
    const reflex___state____state__reflex_web___reflex_web____state = useContext(StateContexts.reflex___state____state__reflex_web___reflex_web____state)



    return(
        (reflex___state____state__reflex_web___reflex_web____state.diff_byte_rows_rx_state_.length+" \u884c")
    )
});

export const Foreach_comp_3ad9251b3d63f349720268bc84ba136d_ed2d5185 = memo(({children}) => {
    const reflex___state____state__reflex_web___reflex_web____state = useContext(StateContexts.reflex___state____state__reflex_web___reflex_web____state)



    return(
        Array.prototype.map.call(reflex___state____state__reflex_web___reflex_web____state.diff_byte_rows_rx_state_ ?? [],((row_rx_state_,index_2f1fc611e8fe86918f7d28083b23e8a8)=>(jsx(Fragment,{key:index_2f1fc611e8fe86918f7d28083b23e8a8},(isTrue(row_rx_state_?.["is_field_header"])?(jsx(Fragment,{},jsx(RadixThemesTable.Row,{},jsx(RadixThemesTable.Cell,{colSpan:4,css:({ ["background"] : ((row_rx_state_?.["status"]?.valueOf?.() === "same"?.valueOf?.()) ? "rgba(156, 163, 175, 0.1)" : ((row_rx_state_?.["status"]?.valueOf?.() === "modified"?.valueOf?.()) ? "rgba(220, 38, 38, 0.1)" : ((row_rx_state_?.["status"]?.valueOf?.() === "added"?.valueOf?.()) ? "rgba(217, 119, 6, 0.1)" : "rgba(229, 231, 235, 0.2)"))) })},jsx(RadixThemesText,{as:"p",css:({ ["fontWeight"] : "bold" }),size:"1"},row_rx_state_?.["field_name"]))))):(jsx(Fragment,{},jsx(RadixThemesTable.Row,{css:({ ["&"] : (!((row_rx_state_?.["status"]?.valueOf?.() === "same"?.valueOf?.())) ? ({ ["background"] : "rgba(220, 38, 38, 0.03)" }) : ({  })) })},jsx(RadixThemesTable.Cell,{css:({ ["fontSize"] : "11px" })},jsx(RadixThemesCode,{variant:"soft"},row_rx_state_?.["offset"])),jsx(RadixThemesTable.Cell,{css:({ ["fontFamily"] : "monospace", ["--default-font-family"] : "monospace", ["fontSize"] : "11px" })},jsx(RadixThemesCode,{variant:"soft"},row_rx_state_?.["left"])),jsx(RadixThemesTable.Cell,{css:({ ["fontFamily"] : "monospace", ["--default-font-family"] : "monospace", ["fontSize"] : "11px" })},jsx(RadixThemesCode,{variant:"soft"},row_rx_state_?.["right"])),jsx(RadixThemesTable.Cell,{},jsx(RadixThemesBadge,{color:((row_rx_state_?.["status"]?.valueOf?.() === "same"?.valueOf?.()) ? "green" : ((row_rx_state_?.["status"]?.valueOf?.() === "modified"?.valueOf?.()) ? "red" : ((row_rx_state_?.["status"]?.valueOf?.() === "added"?.valueOf?.()) ? "amber" : "gray"))),size:"1",variant:"soft"},((row_rx_state_?.["status"]?.valueOf?.() === "same"?.valueOf?.()) ? "=" : ((row_rx_state_?.["status"]?.valueOf?.() === "modified"?.valueOf?.()) ? "\u2260" : ((row_rx_state_?.["status"]?.valueOf?.() === "added"?.valueOf?.()) ? "+" : "-")))))))))))))
    )
});

export const Cond_comp_5b599722ac9e35174ae954bdf92dde38_ed2d5185 = memo(({children}) => {
    const reflex___state____state__reflex_web___reflex_web____state = useContext(StateContexts.reflex___state____state__reflex_web___reflex_web____state)



    return(
        ((reflex___state____state__reflex_web___reflex_web____state.diff_byte_rows_rx_state_.length > 0)?(children?.at?.(0)):(children?.at?.(1)))
    )
});

export const Bare_comp_23613b11dd0eddcbb56bc2ece7d40939_ed2d5185 = memo(({children}) => {
    const reflex___state____state__reflex_web___reflex_web____state = useContext(StateContexts.reflex___state____state__reflex_web___reflex_web____state)



    return(
        reflex___state____state__reflex_web___reflex_web____state.lookup_title_rx_state_
    )
});

export const Bare_comp_c03f7539610792929c93ec2a0435a562_ed2d5185 = memo(({children}) => {
    const reflex___state____state__reflex_web___reflex_web____state = useContext(StateContexts.reflex___state____state__reflex_web___reflex_web____state)



    return(
        (reflex___state____state__reflex_web___reflex_web____state.lookup_results_rx_state_.length+" \u6761")
    )
});

export const Debounceinput_debounceinput_a8476189b5a9153ce58a748937b105e4_ed2d5185 = memo(({children}) => {
    const on_change_48936455dd3797485a9ae17a73742b9f = useCallback(((_e) => (addEvents([(ReflexEvent("reflex___state____state.reflex_web___reflex_web____state.set_lookup_query", ({ ["value"] : _e?.["target"]?.["value"] }), ({  })))], [_e], ({  })))), [addEvents, ReflexEvent])
const reflex___state____state__reflex_web___reflex_web____state = useContext(StateContexts.reflex___state____state__reflex_web___reflex_web____state)



    return(
        jsx(DebounceInput,{css:({ ["width"] : "400px" }),debounceTimeout:300,element:RadixThemesTextField.Root,onChange:on_change_48936455dd3797485a9ae17a73742b9f,placeholder:"\u8f93\u5165\u5173\u952e\u8bcd\u8fc7\u6ee4\uff08DI\u7801/\u540d\u79f0/\u8bf4\u660e\u7b49\uff09...",size:"2",value:(isNotNullOrUndefined(reflex___state____state__reflex_web___reflex_web____state.lookup_query_rx_state_) ? reflex___state____state__reflex_web___reflex_web____state.lookup_query_rx_state_ : "")},)
    )
});

export const Button_button_83114cf2248030633b81fe9c34180ae7_ed2d5185 = memo(({children}) => {
    const on_click_9d15cea15d7a96a2de242daafd99434c = useCallback(((_e) => (addEvents([(ReflexEvent("reflex___state____state.reflex_web___reflex_web____state.do_lookup", ({  }), ({  })))], [_e], ({  })))), [addEvents, ReflexEvent])
const reflex___state____state__reflex_web___reflex_web____state = useContext(StateContexts.reflex___state____state__reflex_web___reflex_web____state)



    return(
        jsx(RadixThemesButton,{color:"blue",loading:reflex___state____state__reflex_web___reflex_web____state.is_loading_rx_state_,onClick:on_click_9d15cea15d7a96a2de242daafd99434c,size:"2"},children)
    )
});

export const Foreach_comp_9db661801aa2aedb77d8ede54606117c_ed2d5185 = memo(({children}) => {
    const reflex___state____state__reflex_web___reflex_web____state = useContext(StateContexts.reflex___state____state__reflex_web___reflex_web____state)



    return(
        Array.prototype.map.call(reflex___state____state__reflex_web___reflex_web____state.lookup_columns_rx_state_ ?? [],((col_rx_state_,index_6b9c8c6486aa763660a257bb1d920398)=>(jsx(RadixThemesTable.ColumnHeaderCell,{key:index_6b9c8c6486aa763660a257bb1d920398},col_rx_state_))))
    )
});

export const Foreach_comp_31ea56be89c9a38c27860aaa87e754e9_ed2d5185 = memo(({children}) => {
    const reflex___state____state__reflex_web___reflex_web____state = useContext(StateContexts.reflex___state____state__reflex_web___reflex_web____state)



    return(
        Array.prototype.map.call(reflex___state____state__reflex_web___reflex_web____state.lookup_results_rx_state_ ?? [],((row_rx_state_,index_8e91129061da00c08f197a6a0c4a3b27)=>(jsx(RadixThemesTable.Row,{key:index_8e91129061da00c08f197a6a0c4a3b27},Array.prototype.map.call(reflex___state____state__reflex_web___reflex_web____state.lookup_columns_rx_state_ ?? [],((col_rx_state_,index_46dff711bf8e3ab6253b6e156e6b90e2)=>(jsx(RadixThemesTable.Cell,{css:({ ["fontSize"] : "12px" }),key:index_46dff711bf8e3ab6253b6e156e6b90e2},jsx(RadixThemesCode,{variant:"soft"},row_rx_state_?.[col_rx_state_])))))))))
    )
});

export const Cond_comp_d7cc7a8dd32ebaf2aa36e33e777b0e4f_ed2d5185 = memo(({children}) => {
    const reflex___state____state__reflex_web___reflex_web____state = useContext(StateContexts.reflex___state____state__reflex_web___reflex_web____state)



    return(
        ((reflex___state____state__reflex_web___reflex_web____state.lookup_results_rx_state_.length > 0)?(children?.at?.(0)):(children?.at?.(1)))
    )
});

export const Cond_comp_7c9b18c4bd8f2fbad6848168352030bc_ed2d5185 = memo(({children}) => {
    const reflex___state____state__reflex_web___reflex_web____state = useContext(StateContexts.reflex___state____state__reflex_web___reflex_web____state)



    return(
        ((reflex___state____state__reflex_web___reflex_web____state.active_tab_rx_state_?.valueOf?.() === "diff"?.valueOf?.())?(children?.at?.(0)):(children?.at?.(1)))
    )
});

export const Cond_comp_7d9debbb946d20f4a805ed22799c676d_ed2d5185 = memo(({children}) => {
    const reflex___state____state__reflex_web___reflex_web____state = useContext(StateContexts.reflex___state____state__reflex_web___reflex_web____state)



    return(
        ((reflex___state____state__reflex_web___reflex_web____state.active_tab_rx_state_?.valueOf?.() === "frame"?.valueOf?.())?(children?.at?.(0)):(children?.at?.(1)))
    )
});

export const Cond_comp_ed098d00589e73cdf97ec0b4816f8c64_ed2d5185 = memo(({children}) => {
    const reflex___state____state__reflex_web___reflex_web____state = useContext(StateContexts.reflex___state____state__reflex_web___reflex_web____state)



    return(
        ((reflex___state____state__reflex_web___reflex_web____state.active_tab_rx_state_?.valueOf?.() === "batch"?.valueOf?.())?(children?.at?.(0)):(children?.at?.(1)))
    )
});

export const Cond_comp_4f8f7efbf7aca7a597ea5cae124a211d_ed2d5185 = memo(({children}) => {
    const reflex___state____state__reflex_web___reflex_web____state = useContext(StateContexts.reflex___state____state__reflex_web___reflex_web____state)



    return(
        ((reflex___state____state__reflex_web___reflex_web____state.active_tab_rx_state_?.valueOf?.() === "single"?.valueOf?.())?(children?.at?.(0)):(children?.at?.(1)))
    )
});
