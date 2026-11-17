/** @typedef {{id:number,code:string,route:string,zone:string,driver:string}} Shipment */
/** @typedef {{id:number,state:'queued'|'running'|'done'|'failed',result:object}} Study */
/** @typedef {{id:number,status:'unmerged'|'pending'|'merged'|'split',version:number,zone:string,display_code:string,exposure:number,excursions:number,loss:number,field_sources:object,pair_count:number,members:Array,active_sample_ids:number[],corrections:Array}} Identity */
/** @typedef {{id:number,field:string,old_value:number,new_value:number,source:string,request_id:string,version:number}} Correction */
/** @typedef {{id:number,study_id:number,note:string,owner:string,status:'draft'|'approved'|'review'}} Recommendation */
