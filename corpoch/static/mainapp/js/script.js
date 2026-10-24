
const isScrolledIntoView = (elem) =>{
    var docViewTop = $(window).scrollTop();
    var docViewBottom = docViewTop + $(window).height();

    var elemTop = $(elem).offset().top;
    var elemBottom = elemTop + $(elem).height();

    return ((elemBottom <= docViewBottom) && (elemTop >= docViewTop));
}

var av_animated = false;
$(document).ready(() =>{
    setTimeout(()=> av_animated=true, 2005);
    $('[data-toggle="tooltip"]').tooltip({placement : 'bottom' , delay : { "show": 500, "hide": 100 }, html : true});
    $('#Logout').tooltip({placement : 'bottom' , delay : { "show": 500, "hide": 100 }, html : true});
    $('.card-img-top').animate({"opacity" : "1.0"}, 10);
    $('img.mx-auto').animate({"opacity" : "1.0"}, 10);

    $(".nav-link, .navbar-brand").click(function (){
        $('html, body').animate({
            scrollTop: $($(this).attr("href")).offset().top
        }, 1000);
    });

    $("#Logout").click(function (){
        $(this)
            .text("")
            .html('<span class="spinner-border"></span>');
    });  
});  
