<<<<<<<< HEAD:hub/hub/static/ui/assets/useCopy-88eDa4c4.js
import{r as n}from"./index-DItMHVED.js";function s(a=1500){const[c,t]=n.useState(!1);async function r(o){try{await navigator.clipboard.writeText(o)}catch{const e=document.createElement("textarea");e.value=o,document.body.appendChild(e),e.select(),document.execCommand("copy"),document.body.removeChild(e)}t(!0),setTimeout(()=>t(!1),a)}return{copied:c,copy:r}}export{s as u};
========
import{r as n}from"./index-DmxdYkp_.js";function s(a=1500){const[c,t]=n.useState(!1);async function r(o){try{await navigator.clipboard.writeText(o)}catch{const e=document.createElement("textarea");e.value=o,document.body.appendChild(e),e.select(),document.execCommand("copy"),document.body.removeChild(e)}t(!0),setTimeout(()=>t(!1),a)}return{copied:c,copy:r}}export{s as u};
>>>>>>>> master:hub/hub/static/ui/assets/useCopy-DhlMaSQh.js
