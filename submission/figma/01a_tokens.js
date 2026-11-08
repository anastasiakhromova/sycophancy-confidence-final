// Figma Plugin API authoring source. Run through Figma MCP use_figma.
// Adapted from figma-generate-library createVariableCollection / createSemanticTokens.
const createdNodeIds=[];
const page=await figma.getNodeByIdAsync('0:1');
await figma.setCurrentPageAsync(page);
page.name='Design System';
for(const style of ['Regular','Medium','Semi Bold','Bold']) await figma.loadFontAsync({family:'Inter',style});
if(page.children.length) throw new Error('Foundations already present: inspect before retry.');
async function createVariableCollection(name,modeNames){const collection=figma.variables.createVariableCollection(name);const modeIds={};collection.renameMode(collection.modes[0].modeId,modeNames[0]);modeIds[modeNames[0]]=collection.modes[0].modeId;return {collection,modeIds};}
function rgb(h){return {r:parseInt(h.slice(1,3),16)/255,g:parseInt(h.slice(3,5),16)/255,b:parseInt(h.slice(5,7),16)/255};}
const {collection,modeIds}=await createVariableCollection('Research / Foundations',['Default']);
const vars={};
function token(name,type,value,scopes){const v=figma.variables.createVariable(name,collection,type);v.setValueForMode(modeIds.Default,value);v.scopes=scopes;v.setVariableCodeSyntax('WEB','var(--research-'+name.replace(/[\s/]+/g,'-').toLowerCase()+')');vars[name]=v;return v;}
for(const [n,h] of Object.entries({ivory:'#F5F3EC',ink:'#171916',muted:'#5F635B',line:'#D6D8CC',panel:'#E9EBE2',white:'#FCFCF8',lime:'#C7F83E'})) token('primitive/'+n,'COLOR',rgb(h),[]);
for(const [n,p,sc] of [['background','ivory',['FRAME_FILL','SHAPE_FILL']],['surface','white',['FRAME_FILL','SHAPE_FILL']],['panel','panel',['FRAME_FILL','SHAPE_FILL']],['text','ink',['TEXT_FILL']],['muted','muted',['TEXT_FILL']],['border','line',['STROKE_COLOR']],['accent','lime',['FRAME_FILL','SHAPE_FILL']],['ink','ink',['FRAME_FILL','SHAPE_FILL','STROKE_COLOR']]]) token('color/'+n,'COLOR',{type:'VARIABLE_ALIAS',id:vars['primitive/'+p].id},sc);
for(const v of [8,16,24,32,48,64,112]) token('space/'+v,'FLOAT',v,['GAP']);
token('radius/16','FLOAT',16,['CORNER_RADIUS']);
const styles={};
for(const [n,size,style,lh] of [['hero',112,'Semi Bold',112],['heading',76,'Semi Bold',82],['subhead',44,'Medium',52],['body',32,'Regular',43],['card',28,'Regular',38],['caption',22,'Regular',30],['label',20,'Semi Bold',26],['number',96,'Semi Bold',100]]){const s=figma.createTextStyle();s.name='Research/'+n;s.fontName={family:'Inter',style};s.fontSize=size;s.lineHeight={unit:'PIXELS',value:lh};styles[n]=s;}

const rp=figma.createPage();rp.name='Research Presentation';return {pageId:rp.id,componentsPageId:page.id,collectionId:collection.id,styles:Object.fromEntries(Object.entries(styles).map(([k,v])=>[k,v.id]))};
