<<<<<<<< HEAD:hub/hub/static/ui/assets/useCopy-8SL9xrfu.js
import{r as n}from"./index-BiW7RXa0.js";function s(a=1500){const[c,t]=n.useState(!1);async function r(o){try{await navigator.clipboard.writeText(o)}catch{const e=document.createElement("textarea");e.value=o,document.body.appendChild(e),e.select(),document.execCommand("copy"),document.body.removeChild(e)}t(!0),setTimeout(()=>t(!1),a)}return{copied:c,copy:r}}export{s as u};
========
import{r as n}from"./index-CadfW2zs.js";function s(a=1500){const[c,t]=n.useState(!1);async function r(o){try{await navigator.clipboard.writeText(o)}catch{const e=document.createElement("textarea");e.value=o,document.body.appendChild(e),e.select(),document.execCommand("copy"),document.body.removeChild(e)}t(!0),setTimeout(()=>t(!1),a)}return{copied:c,copy:r}}export{s as u};
>>>>>>>> agentweave/task/task-352d047b86a3:hub/hub/static/ui/assets/useCopy-B0nsP64y.js
