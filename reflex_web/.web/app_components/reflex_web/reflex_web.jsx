
import {ReflexEvent,applyEventActions,isNotNullOrUndefined,isTrue,pyOr} from "$/utils/state"
import {StateContexts,addEvents} from "$/utils/context"
import {Fragment,memo,useCallback,useContext,useEffect} from "react"
import {jsx} from "@emotion/react"
import {Badge as RadixThemesBadge,Button as RadixThemesButton,Callout as RadixThemesCallout,Card as RadixThemesCard,Code as RadixThemesCode,Flex as RadixThemesFlex,Table as RadixThemesTable,Text as RadixThemesText,TextArea as RadixThemesTextArea,TextField as RadixThemesTextField} from "@radix-ui/themes"
import {DynamicIcon} from "lucide-react/dynamic.mjs"
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

export const Cond_comp_b84525437a6536fe93fc22f52d282ca8_ed2d5185 = memo(({children}) => {
    const reflex___state____state__reflex_web___reflex_web____state = useContext(StateContexts.reflex___state____state__reflex_web___reflex_web____state)



    return(
        ((reflex___state____state__reflex_web___reflex_web____state.current_protocol_rx_state_?.valueOf?.() === 9?.valueOf?.())?(children?.at?.(0)):(children?.at?.(1)))
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

export const Cond_comp_f6d2fc4c7a57e27f3e6366bc92c657bc_ed2d5185 = memo(({children}) => {
    const reflex___state____state__reflex_web___reflex_web____state = useContext(StateContexts.reflex___state____state__reflex_web___reflex_web____state)



    return(
        (pyOr((reflex___state____state__reflex_web___reflex_web____state.current_protocol_rx_state_?.valueOf?.() === 0?.valueOf?.()), () => ((reflex___state____state__reflex_web___reflex_web____state.current_protocol_rx_state_?.valueOf?.() === 6?.valueOf?.())))?(children?.at?.(0)):(children?.at?.(1)))
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

export const Textarea_textarea_68cf146049eb2be99d454557393d861e_ed2d5185 = memo(({children}) => {
    const reflex___state____state__reflex_web___reflex_web____state = useContext(StateContexts.reflex___state____state__reflex_web___reflex_web____state)



    return(
        jsx(RadixThemesTextArea,{css:({ ["& textarea"] : null, ["height"] : "150px", ["width"] : "100%", ["fontFamily"] : "monospace", ["--default-font-family"] : "monospace", ["fontSize"] : "12px", ["readonly"] : true }),placeholder:"\u914d\u7f6e\u53c2\u6570\u540e\u81ea\u52a8\u663e\u793a\u9884\u89c8...",value:reflex___state____state__reflex_web___reflex_web____state.gen_preview_rx_state_},)
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

export const Button_button_db83d85adfafd623b32b75da6499a989_ed2d5185 = memo(({children}) => {
    const on_click_275e3d44b522961b4c388c93da47d34d = useCallback(((_e) => (addEvents([(ReflexEvent("reflex___state____state.reflex_web___reflex_web____state.copy_gen_result", ({  }), ({  })))], [_e], ({  })))), [addEvents, ReflexEvent])
const reflex___state____state__reflex_web___reflex_web____state = useContext(StateContexts.reflex___state____state__reflex_web___reflex_web____state)



    return(
        jsx(RadixThemesButton,{color:"gray",disabled:(reflex___state____state__reflex_web___reflex_web____state.gen_result_rx_state_?.valueOf?.() === ""?.valueOf?.()),onClick:on_click_275e3d44b522961b4c388c93da47d34d,size:"2",variant:"outline"},children)
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

export const Bare_comp_40a280a2ea5b649a40696cd42e5caae5_ed2d5185 = memo(({children}) => {
    const reflex___state____state__reflex_web___reflex_web____state = useContext(StateContexts.reflex___state____state__reflex_web___reflex_web____state)



    return(
        (reflex___state____state__reflex_web___reflex_web____state.diff_result_rx_state_.length+" \u884c")
    )
});

export const Foreach_comp_d1beaa6543df5ee4a985f215d8c07203_ed2d5185 = memo(({children}) => {
    const reflex___state____state__reflex_web___reflex_web____state = useContext(StateContexts.reflex___state____state__reflex_web___reflex_web____state)



    return(
        Array.prototype.map.call(reflex___state____state__reflex_web___reflex_web____state.diff_result_rx_state_ ?? [],((row_rx_state_,index_afeb8dd3503e143d0c23a9388cd1843d)=>(jsx(RadixThemesTable.Row,{css:({ ["&"] : (isTrue(row_rx_state_?.["diff"]) ? ({ ["background"] : "rgba(220, 38, 38, 0.05)" }) : ({  })) }),key:index_afeb8dd3503e143d0c23a9388cd1843d},jsx(RadixThemesTable.Cell,{},jsx(RadixThemesCode,{variant:"soft"},row_rx_state_?.["offset"])),jsx(RadixThemesTable.Cell,{css:({ ["fontFamily"] : "monospace", ["--default-font-family"] : "monospace" })},jsx(RadixThemesCode,{variant:"soft"},row_rx_state_?.["left"])),jsx(RadixThemesTable.Cell,{css:({ ["fontFamily"] : "monospace", ["--default-font-family"] : "monospace" })},jsx(RadixThemesCode,{variant:"soft"},row_rx_state_?.["right"])),jsx(RadixThemesTable.Cell,{},jsx(Fragment,{},(isTrue(row_rx_state_?.["diff"])?(jsx(Fragment,{},jsx(RadixThemesBadge,{color:"red",variant:"soft"},"\u2260"))):(jsx(Fragment,{},jsx(RadixThemesBadge,{color:"green",variant:"soft"},"="))))))))))
    )
});

export const Cond_comp_0be55226f76327a45381e0911e6399b5_ed2d5185 = memo(({children}) => {
    const reflex___state____state__reflex_web___reflex_web____state = useContext(StateContexts.reflex___state____state__reflex_web___reflex_web____state)



    return(
        ((reflex___state____state__reflex_web___reflex_web____state.diff_result_rx_state_.length > 0)?(children?.at?.(0)):(children?.at?.(1)))
    )
});

export const Select_select_33ee04581291402858076565bd4ac0b5_ed2d5185 = memo(({children}) => {
    const on_change_b0305f1338e8b132dba35bf743e6924a = useCallback(((_e) => (addEvents([(ReflexEvent("reflex___state____state.reflex_web___reflex_web____state.set_lookup_type", ({ ["value"] : _e?.["target"]?.["value"] }), ({  })))], [_e], ({  })))), [addEvents, ReflexEvent])



    return(
        jsx("select",{className:"rounded border border-gray-300 px-3 py-2",css:({ ["width"] : "200px" }),defaultValue:"di",onChange:on_change_b0305f1338e8b132dba35bf743e6924a},children)
    )
});

export const Debounceinput_debounceinput_ab4243712103e993335954b7b392c705_ed2d5185 = memo(({children}) => {
    const on_change_48936455dd3797485a9ae17a73742b9f = useCallback(((_e) => (addEvents([(ReflexEvent("reflex___state____state.reflex_web___reflex_web____state.set_lookup_query", ({ ["value"] : _e?.["target"]?.["value"] }), ({  })))], [_e], ({  })))), [addEvents, ReflexEvent])
const reflex___state____state__reflex_web___reflex_web____state = useContext(StateContexts.reflex___state____state__reflex_web___reflex_web____state)



    return(
        jsx(DebounceInput,{css:({ ["width"] : "300px" }),debounceTimeout:300,element:RadixThemesTextField.Root,onChange:on_change_48936455dd3797485a9ae17a73742b9f,placeholder:"\u8f93\u5165\u67e5\u8be2\u7801...",size:"2",value:(isNotNullOrUndefined(reflex___state____state__reflex_web___reflex_web____state.lookup_query_rx_state_) ? reflex___state____state__reflex_web___reflex_web____state.lookup_query_rx_state_ : "")},)
    )
});

export const Button_button_83114cf2248030633b81fe9c34180ae7_ed2d5185 = memo(({children}) => {
    const on_click_9d15cea15d7a96a2de242daafd99434c = useCallback(((_e) => (addEvents([(ReflexEvent("reflex___state____state.reflex_web___reflex_web____state.do_lookup", ({  }), ({  })))], [_e], ({  })))), [addEvents, ReflexEvent])
const reflex___state____state__reflex_web___reflex_web____state = useContext(StateContexts.reflex___state____state__reflex_web___reflex_web____state)



    return(
        jsx(RadixThemesButton,{color:"blue",loading:reflex___state____state__reflex_web___reflex_web____state.is_loading_rx_state_,onClick:on_click_9d15cea15d7a96a2de242daafd99434c,size:"2"},children)
    )
});

export const Bare_comp_c03f7539610792929c93ec2a0435a562_ed2d5185 = memo(({children}) => {
    const reflex___state____state__reflex_web___reflex_web____state = useContext(StateContexts.reflex___state____state__reflex_web___reflex_web____state)



    return(
        (reflex___state____state__reflex_web___reflex_web____state.lookup_results_rx_state_.length+" \u6761")
    )
});

export const Foreach_comp_5af7774eb576a2558b6ca6d02601ac21_ed2d5185 = memo(({children}) => {
    const reflex___state____state__reflex_web___reflex_web____state = useContext(StateContexts.reflex___state____state__reflex_web___reflex_web____state)



    return(
        Array.prototype.map.call(reflex___state____state__reflex_web___reflex_web____state.lookup_results_rx_state_ ?? [],((row_rx_state_,index_65caf505e782197f02a8e662c177432b)=>(jsx(RadixThemesTable.Row,{key:index_65caf505e782197f02a8e662c177432b},jsx(RadixThemesTable.Cell,{},jsx(RadixThemesCode,{variant:"soft"},row_rx_state_?.["code"])),jsx(RadixThemesTable.Cell,{},row_rx_state_?.["name"]),jsx(RadixThemesTable.Cell,{},jsx(RadixThemesText,{as:"p",css:({ ["color"] : "gray" }),size:"1"},row_rx_state_?.["desc"]))))))
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
