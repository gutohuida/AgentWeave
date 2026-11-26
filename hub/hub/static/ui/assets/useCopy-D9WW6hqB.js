<<<<<<<< HEAD:hub/hub/static/ui/assets/useCopy-DzOppnQ0.js
import{r as n}from"./index-Den96b9R.js";function s(a=1500){const[c,t]=n.useState(!1);async function r(o){try{await navigator.clipboard.writeText(o)}catch{const e=document.createElement("textarea");e.value=o,document.body.appendChild(e),e.select(),document.execCommand("copy"),document.body.removeChild(e)}t(!0),setTimeout(()=>t(!1),a)}return{copied:c,copy:r}}export{s as u};
========
import{r as n}from"./index-C6Y7JatB.js";function s(a=1500){const[c,t]=n.useState(!1);async function r(o){try{await navigator.clipboard.writeText(o)}catch{const e=document.createElement("textarea");e.value=o,document.body.appendChild(e),e.select(),document.execCommand("copy"),document.body.removeChild(e)}t(!0),setTimeout(()=>t(!1),a)}return{copied:c,copy:r}}export{s as u};
>>>>>>>> master:hub/hub/static/ui/assets/useCopy-D9WW6hqB.js
